import { timingSafeEqual } from "node:crypto";
// Portable collection rules using built-ins. Counts cross SQL/JSON as strings.
export class Stop extends Error {
  constructor(code) {
    super(code);
    this.code = code;
  }
}
export const fail = (code) => {
  throw new Stop(code);
};
export const LIMITS = Object.freeze({
  attempts: 6,
  handlerMs: 60000,
  marginMs: 15000,
  httpMs: 10000,
  responseBytes: 131072,
  requestBytes: 256,
  leaseSeconds: 75,
  maxRunAttempts: 200,
  maxChannels: 50,
  maxInventory: 10000,
  maxWork: 1000,
});
// Daily for days 0-30 after publication, weekly until day 365, then stop.
// store.mjs applies the same rule in SQL; refreshDue re-checks every row.
export const REFRESH = Object.freeze({
  dailyDays: 30,
  weeklyDays: 365,
  weekDays: 7,
});
const DAY_MS = 86400000;
export function canonical(v) {
  if (Array.isArray(v)) return `[${v.map(canonical).join(",")}]`;
  if (v && typeof v === "object") {
    return `{${
      Object.keys(v).sort().map((k) =>
        `${JSON.stringify(k)}:${canonical(v[k])}`
      ).join(",")
    }}`;
  }
  return JSON.stringify(v);
}
export async function hash(v) {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(canonical(v)),
  );
  return [...new Uint8Array(digest)].map((x) => x.toString(16).padStart(2, "0"))
    .join("");
}
// Hash both bounded strings to fixed-length buffers, then use the native
// constant-time primitive (also supported by Deno's Node compatibility layer).
export async function tokenEqual(a, b) {
  const encode = new TextEncoder();
  const [x, y] = await Promise.all(
    [a, b].map((s) => crypto.subtle.digest("SHA-256", encode.encode(s))),
  );
  return timingSafeEqual(new Uint8Array(x), new Uint8Array(y));
}
export function metric(v) {
  if (v === undefined || v === null) return null;
  if (
    typeof v !== "string" || !/^(0|[1-9][0-9]{0,18})$/.test(v) ||
    BigInt(v) > 9223372036854775807n
  ) fail("INVALID_METRIC");
  return v;
}
export function identifier(v) {
  if (typeof v !== "string" || !/^[A-Za-z0-9_.-]{1,128}$/.test(v)) {
    fail("INVALID_ID");
  }
  return v;
}
export function utc(v) {
  if (
    typeof v !== "string" || !/(Z|[+-][0-9]{2}:[0-9]{2})$/.test(v) ||
    !Number.isFinite(Date.parse(v))
  ) fail("INVALID_TIME");
  return new Date(v).toISOString();
}
// ISO-8601 video duration (PT1H2M3S, P1DT2H, P0D) to whole seconds.
export function duration(v) {
  if (v === undefined || v === null) return null;
  const m = typeof v === "string" &&
    /^P(?:(\d{1,4})D)?(?:T(?:(\d{1,4})H)?(?:(\d{1,5})M)?(?:(\d{1,6})S)?)?$/
      .exec(v);
  if (!m || v === "P" || v.endsWith("T")) fail("INVALID_DURATION");
  const [d, h, min, s] = m.slice(1).map((x) => Number(x ?? 0));
  return ((d * 24 + h) * 60 + min) * 60 + s;
}
const matching = (v, pattern) =>
  typeof v === "string" && pattern.test(v) ? v : null;
function topics(v) {
  if (!Array.isArray(v)) return null;
  return v.filter((x) =>
    typeof x === "string" && x.length <= 200 &&
    /^https:\/\/[a-z]{2,3}\.wikipedia\.org\/wiki\/\S+$/.test(x)
  ).slice(0, 10);
}
export function refreshDue(video, runStart) {
  if (!video.published_at) return true;
  const start = new Date(runStart).getTime();
  const age = Math.floor(
    (start - new Date(video.published_at).getTime()) / DAY_MS,
  );
  if (age <= REFRESH.dailyDays) return true;
  if (age > REFRESH.weeklyDays) return false;
  const last = video.metadata_observed_at
    ? new Date(video.metadata_observed_at).getTime()
    : null;
  return age % REFRESH.weekDays === 0 || last === null ||
    last < start - REFRESH.weekDays * DAY_MS;
}
export function config(get) {
  return {
    active: get("C1_ACTIVATED") === "true",
    token: get("C1_CRON_TOKEN") || "",
    dbUrl: get("C1_COLLECTOR_DB_URL") || "",
    apiKey: get("C1_YOUTUBE_API_KEY") || "",
    cohort: get("C1_COHORT_ID") || "",
    version: get("C1_COHORT_VERSION") || "",
    manifest: get("C1_MANIFEST_HASH") || "",
    retention: get("C1_RETENTION_DECISION_REFERENCE") || "",
  };
}
export function validateConfig(c) {
  if (!c.active) fail("DISABLED");
  if (
    !c.cohort || !c.version || !/^[a-f0-9]{64}$/.test(c.manifest) ||
    !c.retention || !c.apiKey
  ) fail("CONFIGURATION");
  let u;
  try {
    u = new URL(c.dbUrl);
  } catch {
    fail("DATABASE_CONFIGURATION");
  }
  // Explicit TLS requirement; reject alternate routing/options and role override.
  if (
    !["postgres:", "postgresql:"].includes(u.protocol) ||
    decodeURIComponent(u.username) !== "c1_collector" ||
    !u.password || !u.hostname ||
    !["require", "verify-full"].includes(u.searchParams.get("sslmode")) ||
    [...u.searchParams.keys()].some((k) => k !== "sslmode")
  ) fail("DATABASE_CONFIGURATION");
}
export function gate(c, cohort) {
  if (
    !c.active || !cohort || !cohort.enabled ||
    cohort.approval_status !== "approved" ||
    !cohort.approved_by || !cohort.approved_at || !cohort.approval_reference ||
    cohort.manifest_hash !== c.manifest || !c.retention ||
    cohort.retention_decision_reference !== c.retention
  ) fail("GATE_CLOSED");
  const {
    total_attempt_budget: total,
    discovery_attempt_budget: discovery,
    candidate_attempt_reserve: candidates,
    max_pages_per_channel: pages,
    admission_lookback_days: lookback,
    channel_ids: ids,
  } = cohort;
  if (
    ![total, discovery, candidates, pages, lookback].every(Number.isInteger) ||
    lookback < 0 || lookback > 365 ||
    total < 1 || total > LIMITS.maxRunAttempts ||
    discovery < 0 || candidates < 0 || discovery + candidates > total ||
    pages < 1 || pages > 200 ||
    !Array.isArray(ids) || !ids.length || ids.length > LIMITS.maxChannels ||
    new Set(ids).size !== ids.length ||
    cohort.schedule_timezone !== "Asia/Colombo" ||
    !String(cohort.proposed_local_time).startsWith("02:00:00")
  ) fail("CONFIGURATION");
  ids.forEach(identifier);
  return cohort;
}
export function schedule(now) {
  // Colombo 02:00 is UTC 20:30 on the previous calendar date.
  const shifted = new Date(now + 330 * 60000);
  const date = shifted.toISOString().slice(0, 10);
  const start = Date.parse(`${date}T02:00:00+05:30`);
  return {
    date,
    start: new Date(start).toISOString(),
    end: new Date(start + 3600000).toISOString(),
    inWindow: now >= start && now < start + 3600000,
  };
}
export function chunks(ids) {
  const result = [];
  for (let i = 0; i < ids.length; i += 50) result.push(ids.slice(i, i + 50));
  return result;
}
export function discoveryOrder(channels, offset) {
  const sorted = [...channels].sort((a, b) =>
    a.channel_id.localeCompare(b.channel_id)
  );
  const n = sorted.length ? offset % sorted.length : 0;
  return [...sorted.slice(n), ...sorted.slice(0, n)];
}
export function reservation(run, work, cohort, untouchedRefresh) {
  const remaining = cohort.total_attempt_budget - run.attempts_reserved;
  const refreshReserve = untouchedRefresh -
    (work.phase === "refresh" && work.attempts === 0 ? 1 : 0);
  const candidateReserve =
    ["refresh", "channels", "discovery"].includes(work.phase)
      ? cohort.candidate_attempt_reserve
      : 0;
  if (remaining <= refreshReserve + candidateReserve) return "TOTAL_BUDGET";
  if (
    work.phase === "discovery" &&
    run.discovery_attempts >= cohort.discovery_attempt_budget
  ) return "DISCOVERY_BUDGET";
  if (work.attempts >= 3) return "RETRY_LIMIT";
  return null;
}
// owners: stored inventory owner per video, or for candidates the channel whose
// staged discovery page listed it. cutoff: admission_published_after (ISO) or null.
export function normalize(work, payload, allowed, owners = {}, cutoff = null) {
  if (!payload || !Array.isArray(payload.items) || payload.items.length > 50) {
    fail("MALFORMED_RESPONSE");
  }
  const records = [],
    seen = new Set(),
    invalid = [],
    candidates = [],
    skipped = [];
  if (work.phase === "discovery") {
    // Uploads are newest-first; an upload older than the cutoff ends paging.
    let reached = false;
    for (const item of payload.items) {
      const id = identifier(item?.contentDetails?.videoId);
      const owner = item?.snippet?.channelId;
      if (owner && owner !== work.channel_id) fail("OWNERSHIP");
      const published = item?.contentDetails?.videoPublishedAt;
      if (cutoff && published && utc(published) < cutoff) {
        reached = true;
        continue;
      }
      if (!seen.has(id)) candidates.push(id);
      seen.add(id);
    }
    const token = payload.nextPageToken ?? null;
    if (token !== null && (typeof token !== "string" || token.length > 1024)) {
      fail("MALFORMED_RESPONSE");
    }
    return {
      records,
      candidates,
      next: token,
      reached,
      unavailable: [],
      invalid,
      skipped,
    };
  }
  for (const item of payload.items) {
    const id = identifier(item?.id);
    if (!work.selected_ids.includes(id) || seen.has(id)) {
      fail("UNREQUESTED_RESPONSE");
    }
    seen.add(id);
    const channel = work.phase === "channels"
      ? id
      : identifier(item?.snippet?.channelId);
    if (
      !allowed.includes(channel) || (owners[id] && owners[id] !== channel) ||
      (work.phase === "candidates" && owners[id] !== channel)
    ) {
      invalid.push(id);
      continue;
    }
    const s = item.statistics ?? {};
    const text = (v) => typeof v === "string" ? v.slice(0, 512) : null;
    const published = item.snippet?.publishedAt
      ? utc(item.snippet.publishedAt)
      : null;
    if (
      work.phase === "candidates" && cutoff && published && published < cutoff
    ) {
      skipped.push(id);
      continue;
    }
    if (work.phase === "channels") {
      records.push({
        id,
        channel,
        title: text(item.snippet?.title),
        published,
        playlist: item.contentDetails?.relatedPlaylists?.uploads
          ? identifier(item.contentDetails.relatedPlaylists.uploads)
          : null,
        country: matching(item.snippet?.country, /^[A-Z]{2}$/),
        language: matching(
          item.snippet?.defaultLanguage,
          /^[A-Za-z]{2,3}(-[A-Za-z0-9]{1,8}){0,3}$/,
        ),
        topics: topics(item.topicDetails?.topicCategories),
        counts: [
          s.hiddenSubscriberCount === true ? null : metric(s.subscriberCount),
          metric(s.viewCount),
          metric(s.videoCount),
        ],
      });
      continue;
    }
    records.push({
      id,
      channel,
      title: text(item.snippet?.title),
      published,
      duration: duration(item.contentDetails?.duration),
      category: item.snippet?.categoryId === undefined
        ? null
        : identifier(item.snippet.categoryId),
      counts: [
        metric(s.viewCount),
        metric(s.likeCount),
        metric(s.commentCount),
      ],
    });
  }
  return {
    records,
    candidates,
    next: null,
    reached: false,
    invalid,
    skipped,
    unavailable: work.selected_ids.filter((id) => !seen.has(id)),
  };
}
export async function replayCheck(existingHash, incomingHash) {
  if (existingHash !== undefined && existingHash !== incomingHash) {
    fail("REPLAY_CONFLICT");
  }
  return existingHash === undefined ? "insert" : "noop";
}
