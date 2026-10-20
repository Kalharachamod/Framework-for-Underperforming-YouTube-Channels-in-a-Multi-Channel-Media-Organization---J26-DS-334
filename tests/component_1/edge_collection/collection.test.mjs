import test, { before } from "node:test";
import assert from "node:assert/strict";
import net from "node:net";
import tls from "node:tls";
import dgram from "node:dgram";
import { readFileSync } from "node:fs";
import { createHandler } from "../../../supabase/functions/c1-collect/handler.mjs";
import { collect } from "../../../supabase/functions/c1-collect/collector.mjs";
import {
  createYouTube,
  YouTubeError,
} from "../../../supabase/functions/c1-collect/youtube.mjs";
import { PostgresStore } from "../../../supabase/functions/c1-collect/store.mjs";
import { postgresFactory } from "../../../supabase/functions/c1-collect/driver.mjs";
import {
  config,
  discoveryOrder,
  duration,
  gate,
  hash,
  LIMITS,
  metric,
  normalize,
  refreshDue,
  replayCheck,
  reservation,
  schedule,
  Stop,
  validateConfig,
} from "../../../supabase/functions/c1-collect/core.mjs";

before(() => {
  const blocked = () => {
    throw new Error("REAL_NETWORK_FORBIDDEN");
  };
  globalThis.fetch = blocked;
  net.connect = blocked;
  net.createConnection = blocked;
  tls.connect = blocked;
  dgram.createSocket = blocked;
});
const c = {
  active: true,
  token: "synthetic-token-".repeat(4),
  dbUrl:
    "postgres://c1_collector:synthetic@invalid.test/test?sslmode=verify-full",
  apiKey: "synthetic-api",
  cohort: "synthetic-edge",
  version: "test",
  manifest: "a".repeat(64),
  retention: "synthetic-retention",
};
const cohort = () => ({
  cohort_id: c.cohort,
  version: c.version,
  enabled: true,
  approval_status: "approved",
  approved_by: "synthetic",
  approved_at: "2026-10-18T00:00:00Z",
  approval_reference: "synthetic",
  manifest_hash: c.manifest,
  retention_decision_reference: c.retention,
  total_attempt_budget: 10,
  discovery_attempt_budget: 3,
  candidate_attempt_reserve: 2,
  max_pages_per_channel: 10,
  admission_lookback_days: 30,
  channel_ids: ["a", "b", "c"],
  schedule_timezone: "Asia/Colombo",
  proposed_local_time: "02:00:00",
});
const env = () => ({
  C1_ACTIVATED: "true",
  C1_CRON_TOKEN: c.token,
  C1_COLLECTOR_DB_URL: c.dbUrl,
  C1_YOUTUBE_API_KEY: c.apiKey,
  C1_COHORT_ID: c.cohort,
  C1_COHORT_VERSION: c.version,
  C1_MANIFEST_HASH: c.manifest,
  C1_RETENTION_DECISION_REFERENCE: c.retention,
});
const request = (
  token = c.token,
  body = { action: "daily-start" },
  method = "POST",
) =>
  new Request("https://synthetic.invalid", {
    method,
    headers: {
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
    },
    ...(method === "POST" ? { body: JSON.stringify(body) } : {}),
  });
const work = (extra = {}) => ({
  work_id: "synthetic-work",
  run_id: "synthetic-run",
  cohort_id: c.cohort,
  version: c.version,
  phase: "refresh",
  selected_ids: ["v"],
  channel_id: null,
  attempts: 0,
  status: "pending",
  outcomes: {},
  ...extra,
});
const payload = (statistics = { viewCount: "0" }, channel = "a") => ({
  items: [{
    id: "v",
    snippet: { channelId: channel, title: "Synthetic" },
    statistics,
  }],
});
function handlerFixture(values = env(), options = {}) {
  const calls = { connections: 0, api: 0, closed: 0 };
  const handler = createHandler({
    get: (k) => values[k],
    openStore: async () => {
      calls.connections++;
      return {
        close: async () => {
          calls.closed++;
        },
      };
    },
    createTransport: () => {
      calls.api++;
      return {};
    },
    collect: async () => ({ state: "synthetic" }),
    ...options,
  });
  return { handler, calls };
}
test("unauthenticated, wrong, oversized and missing configured tokens cause zero connections/API", async () => {
  for (const token of ["", "wrong", "x".repeat(1000)]) {
    const { handler, calls } = handlerFixture();
    assert.equal((await handler(request(token))).status, 401);
    assert.deepEqual(calls, { connections: 0, api: 0, closed: 0 });
  }
  const { handler, calls } = handlerFixture({
    ...env(),
    C1_CRON_TOKEN: undefined,
  });
  assert.equal((await handler(request())).status, 401);
  assert.equal(calls.connections, 0);
});
test("activation absent/false fails before connection/API; only exact true enables", async () => {
  for (const value of [undefined, "false", "TRUE", "1"]) {
    const { handler, calls } = handlerFixture({
      ...env(),
      C1_ACTIVATED: value,
    });
    assert.equal((await handler(request())).status, 503);
    assert.equal(calls.connections, 0);
    assert.equal(calls.api, 0);
  }
  assert.equal(config(() => undefined).active, false);
});
test("authenticated input shape and size are bounded before DB", async () => {
  for (
    const body of [{ action: "daily-start", ids: ["v"] }, { action: "other" }, {
      action: "x".repeat(300),
    }, null]
  ) {
    const { handler, calls } = handlerFixture();
    assert.ok((await handler(request(c.token, body))).status >= 400);
    assert.equal(calls.connections, 0);
  }
  const { handler, calls } = handlerFixture();
  assert.equal((await handler(request(c.token, {}, "GET"))).status, 405);
  assert.equal(calls.connections, 0);
});
test("only dedicated credential, role and TLS accepted; no fallback", async () => {
  validateConfig(c);
  for (
    const url of [
      "",
      "postgres://postgres:synthetic@invalid.test/db?sslmode=require",
      "postgres://c1_collector:synthetic@invalid.test/db",
      c.dbUrl + "&options=role%3Dpostgres",
    ]
  ) assert.throws(() => validateConfig({ ...c, dbUrl: url }), Stop);
  const { handler, calls } = handlerFixture({
    ...env(),
    C1_COLLECTOR_DB_URL: undefined,
    SUPABASE_DB_URL: c.dbUrl,
  });
  assert.equal((await handler(request())).status, 503);
  assert.equal(calls.connections, 0);
});
test("driver adapter is lazy, pins TLS verification, disables prepare, and binds arrays explicitly", async () => {
  let loads = 0, options, url, parameters, closed = false;
  const factory = postgresFactory(async () => {
    loads++;
    return {
      default: (u, o) => {
        options = o;
        url = u;
        return {
          begin: async (body) =>
            body({
              unsafe: async (_sql, args) => {
                parameters = args;
                return [];
              },
            }),
          array: (value, oid) => ({ value, oid }),
          end: async () => {
            closed = true;
          },
        };
      },
    };
  }, () => true);
  assert.equal(loads, 0);
  const store = await factory(c);
  assert.equal(loads, 1);
  assert.equal(options.max, 1);
  assert.equal(options.prepare, false);
  assert.equal(options.ssl.rejectUnauthorized, true);
  assert.equal(new URL(url).username, "c1_collector");
  assert.equal(new URL(url).search, "");
  await store.db.transaction((q) => q("SELECT $1::text[]", [["synthetic"]]));
  assert.deepEqual(parameters, [{ value: ["synthetic"], oid: 25 }]);
  await store.close();
  assert.equal(closed, true);
});
test("sanitized unknown errors and connection cleanup", async () => {
  const { handler, calls } = handlerFixture(env(), {
    collect: async () => {
      throw new Error("secret-host-password");
    },
  });
  const res = await handler(request());
  assert.equal(res.status, 503);
  assert.equal((await res.text()).includes("secret"), false);
  assert.equal(calls.closed, 1);
});
test("pending, disabled, manifest and retention mismatch gates are closed", () => {
  for (
    const patch of [
      { enabled: false },
      { approval_status: "pending" },
      { manifest_hash: "b".repeat(64) },
      { retention_decision_reference: null },
      { retention_decision_reference: "other" },
      { approved_by: null },
    ]
  ) assert.throws(() => gate(c, { ...cohort(), ...patch }), Stop);
  gate(c, cohort());
});
test("NULL, hidden subscriber, zero, maximum bigint and invalid counts", () => {
  assert.equal(metric(undefined), null);
  assert.equal(metric("0"), "0");
  assert.equal(metric("9223372036854775807"), "9223372036854775807");
  for (
    const n of [-1, 0, 9007199254740992, "-1", "9223372036854775808", "1.1"]
  ) assert.throws(() => metric(n), Stop);
  const row =
    normalize(work(), payload({ viewCount: "9007199254740993" }), ["a"], {
      v: "a",
    }).records[0];
  assert.deepEqual(row.counts, ["9007199254740993", null, null]);
  const hidden = normalize(work({ phase: "channels", selected_ids: ["a"] }), {
    items: [{
      id: "a",
      statistics: { hiddenSubscriberCount: true, subscriberCount: "0" },
    }],
  }, ["a"]);
  assert.equal(hidden.records[0].counts[0], null);
});
test("missing videos produce unavailable outcomes, no fake zero observations", () => {
  const result = normalize(work(), { items: [] }, ["a"], { v: "a" });
  assert.deepEqual(result.unavailable, ["v"]);
  assert.deepEqual(result.records, []);
});
test("candidate and stable inventory ownership validation; unexpected IDs fail", () => {
  assert.deepEqual(
    normalize(work(), payload({}, "b"), ["a", "b"], { v: "a" }).invalid,
    ["v"],
  );
  assert.deepEqual(
    normalize(
      work({ phase: "candidates", channel_id: "a" }),
      payload({}, "b"),
      ["a", "b"],
    ).invalid,
    ["v"],
  );
  assert.throws(
    () => normalize(work({ selected_ids: ["other"] }), payload(), ["a"]),
    Stop,
  );
});
test("fair discovery rotates start, preserves round order, and validates page tokens", () => {
  const channels = ["c", "a", "b"].map((channel_id) => ({ channel_id }));
  assert.deepEqual(discoveryOrder(channels, 1).map((x) => x.channel_id), [
    "b",
    "c",
    "a",
  ]);
  const rounds = [0, 1].flatMap((round) =>
    discoveryOrder(channels, 1).map((x, i) => ({
      channel: x.channel_id,
      order: round * 3 + i,
    }))
  );
  assert.deepEqual(
    rounds.sort((a, b) => a.order - b.order).map((x) => x.channel),
    ["b", "c", "a", "b", "c", "a"],
  );
  assert.equal(
    normalize(work({ phase: "discovery", channel_id: "a" }), {
      items: [],
      nextPageToken: "next",
    }, ["a"]).next,
    "next",
  );
  assert.throws(
    () =>
      normalize(work({ phase: "discovery" }), {
        items: [],
        nextPageToken: "x".repeat(1025),
      }, ["a"]),
    Stop,
  );
});
test("budgets include retries and protect initial refresh and candidates", () => {
  const co = cohort(), run = { attempts_reserved: 7, discovery_attempts: 0 };
  assert.equal(reservation(run, work({ attempts: 1 }), co, 1), "TOTAL_BUDGET");
  assert.equal(
    reservation(
      { attempts_reserved: 0, discovery_attempts: 3 },
      work({ phase: "discovery" }),
      co,
      0,
    ),
    "DISCOVERY_BUDGET",
  );
  assert.equal(
    reservation({ attempts_reserved: 0 }, work({ attempts: 3 }), co, 0),
    "RETRY_LIMIT",
  );
  assert.equal(reservation({ attempts_reserved: 7 }, work(), co, 1), null);
});
test("Colombo schedule uses preceding UTC date and bounded window", () => {
  const s = schedule(Date.parse("2026-10-17T20:45:00Z"));
  assert.equal(s.start, "2026-10-17T20:30:00.000Z");
  assert.equal(s.date, "2026-10-18");
  assert.equal(s.inWindow, true);
  assert.equal(schedule(Date.parse("2026-10-17T21:30:00Z")).inWindow, false);
});
test("production-default claim rejects an out-of-window database time", async () => {
  const f = dbFixture({
    clock: () => Date.parse("2026-10-17T21:30:00Z"),
    coord: { active_run_id: null, lease_owner: null, lease_expires_at: null },
  });
  assert.equal((await f.store.claim(c, "daily-start")).state, "no_active_run");
});
test("injected internal scheduling clock permits an otherwise valid claim", async () => {
  const f = dbFixture({
    clock: () => Date.parse("2026-10-17T20:45:00Z"),
    coord: { lease_owner: null, lease_expires_at: null },
    respond: (sql) =>
      sql.includes("RETURNING fence")
        ? [{ fence: "3" }]
        : sql.startsWith("SELECT run_id FROM")
        ? []
        : sql.startsWith("SELECT channel_id FROM")
        ? [{ channel_id: "a" }, { channel_id: "b" }, { channel_id: "c" }]
        : sql.startsWith("SELECT video_id,published_at")
        ? [{ video_id: "v" }]
        : undefined,
  });
  assert.ok((await f.store.claim(c, "daily-start")).lease);
});

// Scripted DB implements only the injected query boundary. No driver loaded.
function dbFixture(
  {
    coord = {},
    run = {},
    w = {},
    respond = () => undefined,
    identity = { session_user: "c1_collector", current_user: "c1_collector" },
    co = cohort(),
    clock = () => Date.parse("2026-10-17T20:45:00Z"),
  } = {},
) {
  const calls = [];
  const lease = { run: "synthetic-run", owner: "synthetic-owner", fence: "2" };
  const coordination = {
    active_run_id: lease.run,
    lease_owner: lease.owner,
    fence: "2",
    inventory_revision: "1",
    discovery_start_offset: 1,
    admission_published_after: null,
    lease_expires_at: "2026-10-17T20:47:00Z",
    db_now: "2026-10-17T20:45:00Z",
    ...coord,
  };
  const currentRun = {
    run_id: lease.run,
    cohort_id: c.cohort,
    version: c.version,
    phase: "refresh",
    status: "running",
    attempts_reserved: 0,
    discovery_attempts: 0,
    scheduled_for: "2026-10-17T20:30:00Z",
    deadline_at: "2026-10-17T21:30:00Z",
    summary: {},
    ...run,
  };
  const currentWork = work({
    lease_owner: lease.owner,
    fence: lease.fence,
    ...w,
  });
  const db = {
    transaction: async (body) =>
      body(async (sql, args = []) => {
        calls.push({ sql, args });
        const result = await respond(sql, args, {
          coordination,
          currentRun,
          currentWork,
        });
        if (result !== undefined) return result;
        if (sql.startsWith("SET LOCAL")) return [];
        if (sql === "SELECT session_user, current_user") return [identity];
        if (sql.startsWith("SELECT * FROM c1.cohorts")) return [co];
        if (
          sql.includes("FROM c1.collection_coordination") &&
          sql.includes("FOR UPDATE")
        ) return [coordination];
        if (sql.startsWith("SELECT * FROM c1.collection_runs")) {
          return [currentRun];
        }
        if (sql.startsWith("SELECT * FROM c1.collection_work")) {
          return [currentWork];
        }
        if (sql.includes("FROM c1.collection_work WHERE run_id=$1 ORDER")) {
          return [currentWork];
        }
        if (sql.startsWith("SELECT video_id,channel_id")) {
          return [{ video_id: "v", channel_id: "a" }];
        }
        if (sql.startsWith("SELECT payload_hash")) {
          return [];
        }
        if (sql.startsWith("SELECT w.channel_id")) return [];
        if (sql.startsWith("UPDATE") || sql.startsWith("INSERT")) return [];
        throw new Error(`Unmocked query: ${sql}`);
      }),
    close: async () => {},
  };
  return {
    store: new PostgresStore(db, c, { scheduleClock: clock }),
    calls,
    lease,
    coordination,
    currentWork,
    currentRun,
  };
}
test("actual store rejects wrong SQL session login and pending gate before coordination writes", async () => {
  for (
    const options of [
      { identity: { session_user: "postgres", current_user: "c1_collector" } },
      { co: { ...cohort(), enabled: false } },
      { co: { ...cohort(), approval_status: "pending" } },
    ]
  ) {
    const f = dbFixture(options);
    await assert.rejects(
      () => f.store.reserve(f.lease, "synthetic-work"),
      Stop,
    );
    assert.equal(f.calls.some((x) => x.sql.startsWith("UPDATE")), false);
  }
});
test("authenticated request still makes no API request when database cohort gate is pending", async () => {
  const f = dbFixture({ co: { ...cohort(), approval_status: "pending" } });
  let requests = 0;
  const { handler } = handlerFixture(env(), {
    openStore: async () => f.store,
    collect,
    createTransport: () => ({
      request: async () => {
        requests++;
        return payload();
      },
    }),
  });
  const response = await handler(request());
  assert.equal(response.status, 503);
  assert.equal(requests, 0);
});
test("disabling activation after staging rejects the commit before any write", async () => {
  const f = dbFixture();
  f.store.active = () => false;
  await assert.rejects(
    () => f.store.commit(f.lease, "synthetic-work"),
    /GATE_CLOSED/,
  );
  assert.equal(
    f.calls.some((x) =>
      x.sql.startsWith("UPDATE") || x.sql.startsWith("INSERT")
    ),
    false,
  );
});
test("actual claim blocks concurrent worker, takes over expired lease and increments fence", async () => {
  const busy = dbFixture();
  assert.equal((await busy.store.claim(c, "daily-start")).state, "busy");
  const takeover = dbFixture({
    coord: { lease_expires_at: "2026-10-17T20:44:00Z" },
    respond: (sql) =>
      sql.includes("RETURNING fence") ? [{ fence: "3" }] : undefined,
  });
  const result = await takeover.store.claim(c, "continuation");
  assert.equal(result.lease.fence, "3");
  assert.ok(takeover.calls.find((x) => x.sql.includes("fence=fence+1")));
});
test("continuation never creates daily run and completed daily invocation is idempotent", async () => {
  const empty = dbFixture({ coord: { active_run_id: null } });
  assert.equal(
    (await empty.store.claim(c, "continuation")).state,
    "no_active_run",
  );
  assert.equal(empty.calls.some((x) => x.sql.startsWith("INSERT")), false);
  const done = dbFixture({
    run: { status: "complete" },
    respond: (sql) =>
      sql.startsWith("SELECT run_id FROM")
        ? [{ run_id: "finished" }]
        : undefined,
  });
  assert.equal(
    (await done.store.claim(c, "daily-start")).state,
    "already_finished",
  );
  assert.equal(done.calls.some((x) => x.sql.startsWith("INSERT")), false);
});
test("actual claim freezes due inventory, batches all IDs, and rejects insufficient initial budget", async () => {
  const fixture = () =>
    dbFixture({
      coord: { active_run_id: null },
      respond: (sql) => {
        if (sql.startsWith("SELECT run_id FROM")) return [];
        if (sql.startsWith("SELECT channel_id FROM")) {
          return ["a", "b", "c"].map((channel_id) => ({ channel_id }));
        }
        if (sql.startsWith("SELECT video_id,published_at")) {
          return Array.from({ length: 61 }, (_, i) => ({ video_id: `v${i}` }));
        }
        if (sql.startsWith("INSERT INTO c1.collection_runs")) {
          return [{
            run_id: "new-run",
            cohort_id: c.cohort,
            version: c.version,
          }];
        }
        if (sql.includes("RETURNING fence")) return [{ fence: "3" }];
      },
    });
  const f = fixture();
  await f.store.claim(c, "daily-start");
  const batches = f.calls.filter((x) =>
    x.sql.startsWith("INSERT INTO c1.collection_work") &&
    x.args[5] === "refresh"
  );
  assert.deepEqual(batches.map((x) => x.args[6].length), [50, 11]);
  const small = dbFixture({
    coord: { active_run_id: null },
    co: { ...cohort(), total_attempt_budget: 4, discovery_attempt_budget: 0 },
    respond: (sql) => {
      if (sql.startsWith("SELECT run_id FROM")) return [];
      if (sql.startsWith("SELECT channel_id FROM")) {
        return ["a", "b", "c"].map((channel_id) => ({ channel_id }));
      }
      if (sql.startsWith("SELECT video_id,published_at")) {
        return Array.from({ length: 61 }, (_, i) => ({ video_id: `v${i}` }));
      }
    },
  });
  await assert.rejects(
    () => small.store.claim(c, "daily-start"),
    /INITIAL_BUDGET/,
  );
  assert.equal(small.calls.some((x) => x.sql.startsWith("INSERT")), false);
});
test("claim sets the admission cutoff once and refreshes only videos that are due", async () => {
  const f = dbFixture({
    coord: { active_run_id: null },
    respond: (sql) => {
      if (sql.startsWith("SELECT run_id FROM")) return [];
      if (sql.startsWith("SELECT channel_id FROM")) {
        return ["a", "b", "c"].map((channel_id) => ({ channel_id }));
      }
      if (sql.startsWith("SELECT video_id,published_at")) {
        return [
          { video_id: "new", published_at: "2026-10-14T20:30:00Z" },
          // Not due (age 100, observed 2 days ago): the JS re-check drops it.
          {
            video_id: "old",
            published_at: "2026-07-09T20:30:00Z",
            metadata_observed_at: "2026-10-15T21:00:00Z",
          },
        ];
      }
      if (sql.startsWith("INSERT INTO c1.collection_runs")) {
        return [{ run_id: "new-run", cohort_id: c.cohort, version: c.version }];
      }
      if (sql.includes("RETURNING fence")) return [{ fence: "3" }];
    },
  });
  await f.store.claim(c, "daily-start");
  const cutoff = f.calls.find((x) =>
    x.sql.includes("SET admission_published_after")
  );
  assert.ok(cutoff.sql.includes("admission_published_after IS NULL"));
  assert.deepEqual(cutoff.args.slice(0, 2), ["2026-10-17T20:30:00.000Z", 30]);
  const due = f.calls.find((x) =>
    x.sql.startsWith("SELECT video_id,published_at")
  );
  assert.deepEqual(due.args.slice(3), [
    "2026-10-17T20:30:00.000Z",
    30,
    365,
    7,
    LIMITS.maxInventory + 1,
  ]);
  const refresh = f.calls.filter((x) =>
    x.sql.startsWith("INSERT INTO c1.collection_work") &&
    x.args[5] === "refresh"
  );
  assert.deepEqual(refresh.map((x) => x.args[6]), [["new"]]);
});
test("refresh policy: daily to day 30, weekly to day 365 with catch-up, then stop", () => {
  const start = "2026-10-17T20:30:00.000Z";
  const ago = (days) =>
    new Date(Date.parse(start) - days * 86400000).toISOString();
  const recent = ago(1);
  assert.equal(refreshDue({ published_at: null }, start), true);
  assert.equal(refreshDue({ published_at: ago(0) }, start), true);
  assert.equal(
    refreshDue({ published_at: ago(30), metadata_observed_at: recent }, start),
    true,
  );
  assert.equal(
    refreshDue({ published_at: ago(31), metadata_observed_at: recent }, start),
    false,
  );
  assert.equal(
    refreshDue({ published_at: ago(35), metadata_observed_at: recent }, start),
    true,
  );
  assert.equal(
    refreshDue({ published_at: ago(40), metadata_observed_at: ago(9) }, start),
    true,
  );
  assert.equal(refreshDue({ published_at: ago(40) }, start), true);
  assert.equal(
    refreshDue({ published_at: ago(364), metadata_observed_at: ago(6) }, start),
    true,
  );
  assert.equal(
    refreshDue(
      { published_at: ago(366), metadata_observed_at: ago(30) },
      start,
    ),
    false,
  );
});
test("video duration and category, channel country/language/topics are parsed and bounded", () => {
  assert.equal(duration(undefined), null);
  assert.equal(duration("PT1H2M3S"), 3723);
  assert.equal(duration("P1DT2H"), 93600);
  assert.equal(duration("P0D"), 0);
  assert.equal(duration("PT45S"), 45);
  for (const bad of ["P", "PT", "P1W", "1H", "PT-1S", 30]) {
    assert.throws(() => duration(bad), /INVALID_DURATION/);
  }
  const video = normalize(
    work(),
    {
      items: [{
        id: "v",
        snippet: { channelId: "a", title: "Synthetic", categoryId: "22" },
        contentDetails: { duration: "PT1M" },
        statistics: { viewCount: "5" },
      }],
    },
    ["a"],
    { v: "a" },
  ).records[0];
  assert.equal(video.duration, 60);
  assert.equal(video.category, "22");
  const channel = normalize(work({ phase: "channels", selected_ids: ["a"] }), {
    items: [{
      id: "a",
      snippet: { title: "Synthetic", country: "LK", defaultLanguage: "si" },
      topicDetails: {
        topicCategories: [
          "https://en.wikipedia.org/wiki/Entertainment",
          "javascript:alert(1)",
          ...Array.from(
            { length: 12 },
            (_, i) => `https://en.wikipedia.org/wiki/T${i}`,
          ),
        ],
      },
      statistics: {},
    }],
  }, ["a"]).records[0];
  assert.equal(channel.country, "LK");
  assert.equal(channel.language, "si");
  assert.equal(channel.topics.length, 10);
  assert.ok(
    channel.topics.every((t) => t.startsWith("https://en.wikipedia.org/wiki/")),
  );
  const odd = normalize(work({ phase: "channels", selected_ids: ["a"] }), {
    items: [{
      id: "a",
      snippet: { country: "Sri Lanka", defaultLanguage: "x" },
      statistics: {},
    }],
  }, ["a"]).records[0];
  assert.deepEqual([odd.country, odd.language, odd.topics], [null, null, null]);
});
test("discovery stops at the admission cutoff and older candidates are skipped", () => {
  const cutoff = "2026-09-17T20:30:00.000Z";
  const page = normalize(
    work({ phase: "discovery", channel_id: "a" }),
    {
      items: [
        {
          contentDetails: {
            videoId: "fresh",
            videoPublishedAt: "2026-10-01T00:00:00Z",
          },
        },
        {
          contentDetails: {
            videoId: "stale",
            videoPublishedAt: "2026-09-01T00:00:00Z",
          },
        },
      ],
      nextPageToken: "more",
    },
    ["a"],
    {},
    cutoff,
  );
  assert.deepEqual(page.candidates, ["fresh"]);
  assert.equal(page.reached, true);
  const candidates = normalize(
    work({ phase: "candidates", selected_ids: ["v"] }),
    {
      items: [{
        id: "v",
        snippet: { channelId: "a", publishedAt: "2026-09-01T00:00:00Z" },
        statistics: {},
      }],
    },
    ["a"],
    { v: "a" },
    cutoff,
  );
  assert.deepEqual(candidates.skipped, ["v"]);
  assert.deepEqual(candidates.records, []);
});
test("gate accepts the 41-channel 200/70/20 plan and rejects over-cap or bad lookback", () => {
  const ids = Array.from({ length: 41 }, (_, i) => `ch${i}`);
  const plan = {
    ...cohort(),
    channel_ids: ids,
    total_attempt_budget: 200,
    discovery_attempt_budget: 70,
    candidate_attempt_reserve: 20,
  };
  gate(c, plan);
  for (
    const patch of [
      { total_attempt_budget: 201 },
      { admission_lookback_days: -1 },
      { admission_lookback_days: 366 },
      { admission_lookback_days: null },
    ]
  ) assert.throws(() => gate(c, { ...plan, ...patch }), /CONFIGURATION/);
});
test("actual scheduler seeds rotated discovery only after refresh and channel tasks finish", async () => {
  let seeded = false;
  const f = dbFixture({
    run: { summary: { rotation: 1, discoverySeeded: false } },
    respond: (sql) => {
      if (
        sql.includes("FROM c1.collection_work WHERE run_id=$1 ORDER")
      ) {
        return seeded ? [work({ phase: "discovery", channel_id: "b" })] : [];
      }
      if (sql.startsWith("SELECT channel_id,uploads_playlist_id")) {
        return ["a", "b", "c"].map((channel_id) => ({
          channel_id,
          uploads_playlist_id: `uploads_${channel_id}`,
        }));
      }
      if (sql.startsWith("UPDATE c1.collection_runs SET summary=")) {
        seeded = true;
        return [];
      }
    },
  });
  const next = await f.store.next(f.lease);
  assert.equal(next.phase, "discovery");
  const inserts = f.calls.filter((x) =>
    x.sql.startsWith("INSERT INTO c1.collection_work")
  );
  assert.deepEqual(inserts.map((x) => x.args[7]), ["b", "c", "a"]);
  assert.deepEqual(inserts.map((x) => x.args[9]), [0, 1, 2]);
});
test("actual store fences reject takeover, expired lease, wrong owner and wrong run before stage/commit", async () => {
  for (
    const coord of [{ fence: "3" }, { lease_owner: "new-worker" }, {
      active_run_id: "other-run",
    }, { lease_expires_at: "2026-10-17T20:44:59Z" }]
  ) {
    const f = dbFixture({ coord, w: { status: "claimed" } });
    await assert.rejects(
      () =>
        f.store.stage(
          f.lease,
          "synthetic-work",
          payload(),
          "2026-10-17T20:45:00Z",
          "x",
        ),
      /LEASE_LOST/,
    );
    await assert.rejects(
      () => f.store.commit(f.lease, "synthetic-work"),
      /LEASE_LOST/,
    );
    assert.equal(
      f.calls.some((x) =>
        x.sql.startsWith("UPDATE") || x.sql.startsWith("INSERT")
      ),
      false,
    );
  }
});
test("durable reservation increments run/work before transport and is bounded", async () => {
  const f = dbFixture({
    respond: (sql, _args, { currentWork }) =>
      sql.startsWith("UPDATE c1.collection_work SET status=")
        ? [{ ...currentWork, attempts: 1, status: "claimed" }]
        : undefined,
  });
  const ready = await f.store.reserve(f.lease, "synthetic-work");
  assert.equal(ready.attempts, 1);
  assert.ok(
    f.calls.find((x) =>
      x.sql.includes("attempts_reserved=attempts_reserved+1")
    ),
  );
  const exhausted = dbFixture({ run: { attempts_reserved: 10 } });
  assert.equal(
    await exhausted.store.reserve(exhausted.lease, "synthetic-work"),
    null,
  );
  assert.equal(
    exhausted.calls.some((x) =>
      x.sql.includes("attempts_reserved=attempts_reserved+1")
    ),
    false,
  );
});
test("staging writes response and original UTC time once; conflicting staging rejected", async () => {
  const p = payload(),
    digest = await hash(p),
    observed = "2026-10-17T20:45:01.000Z";
  const f = dbFixture({ w: { status: "claimed" } });
  await f.store.stage(f.lease, "synthetic-work", p, observed, digest);
  const update = f.calls.find((x) => x.sql.includes("SET staged_response="));
  assert.equal(update.args[1], observed);
  assert.equal(update.args[2], digest);
  const replay = dbFixture({
    w: {
      status: "staged",
      staged_response: p,
      payload_hash: digest,
      observed_at: observed,
    },
  });
  await replay.store.stage(replay.lease, "synthetic-work", p, observed, digest);
  assert.equal(replay.calls.some((x) => x.sql.startsWith("UPDATE")), false);
  await assert.rejects(
    () =>
      replay.store.stage(
        replay.lease,
        "synthetic-work",
        p,
        "2026-10-17T20:45:02.000Z",
        digest,
      ),
    /REPLAY_CONFLICT/,
  );
});
test("actual snapshot writer identical replay is no-op, conflict never overwrites", async () => {
  const f = dbFixture(),
    w = work(),
    record = { id: "v", counts: [null, "0", "9007199254740993"] };
  for (const phase of ["refresh", "channels"]) {
    const writes = [];
    await f.store.snapshot(
      async (sql, args) => {
        writes.push({ sql, args });
        return sql.startsWith("SELECT") ? [{ payload_hash: "same" }] : [];
      },
      { ...w, phase },
      record,
      "2026-10-17T20:45:00Z",
      "same",
    );
    assert.equal(writes.length, 1);
    await assert.rejects(
      () =>
        f.store.snapshot(
          async () => [{ payload_hash: "other" }],
          { ...w, phase },
          record,
          "2026-10-17T20:45:00Z",
          "same",
        ),
      /REPLAY_CONFLICT/,
    );
  }
  assert.equal(await replayCheck(undefined, "x"), "insert");
});
test("actual staged commit after crash uses stored time, NULL and bigint; late metadata guarded", async () => {
  const p = payload({ viewCount: "9007199254740993" }),
    observed = "2026-10-17T20:44:00.000Z";
  const f = dbFixture({
    w: {
      status: "staged",
      staged_response: p,
      payload_hash: await hash(p),
      observed_at: observed,
    },
  });
  await f.store.commit(f.lease, "synthetic-work");
  const insert = f.calls.find((x) =>
    x.sql.startsWith("INSERT INTO c1.video_stats_history")
  );
  // Keyed (video_id, observed_at); channel_id and cohort/run are provenance.
  assert.deepEqual(insert.args.slice(0, 3), ["v", "a", observed]);
  assert.deepEqual(insert.args.slice(3, 5), [c.cohort, c.version]);
  assert.deepEqual(insert.args.slice(7, 10), ["9007199254740993", null, null]);
  const lookup = f.calls.find((x) =>
    x.sql.includes("FROM c1.video_stats_history")
  );
  assert.deepEqual(lookup.args, ["v", observed]);
  assert.ok(f.calls.find((x) => x.sql.includes("metadata_observed_at<=$5")));
});
test("actual store missing video creates outcome without history or inventory deletion", async () => {
  const p = { items: [] };
  const f = dbFixture({
    w: {
      status: "staged",
      staged_response: p,
      payload_hash: await hash(p),
      observed_at: "2026-10-17T20:44:00Z",
    },
  });
  await f.store.commit(f.lease, "synthetic-work");
  assert.equal(
    f.calls.some((x) => x.sql.startsWith("INSERT INTO c1.video_stats_history")),
    false,
  );
  const outcome = f.calls.find((x) => x.sql.includes("SET status='committed'"));
  assert.deepEqual(JSON.parse(outcome.args[1]).unavailable, ["v"]);
  assert.equal(f.calls.some((x) => /DELETE|TRUNCATE/.test(x.sql)), false);
});
test("actual store fatal auth/quota closes run; transient retry persists next-attempt without sleeping", async () => {
  for (const code of ["API_AUTH", "QUOTA", "TRANSIENT"]) {
    const f = dbFixture({ w: { status: "claimed", attempts: 1 } });
    await f.store.failed(f.lease, "synthetic-work", {
      code,
      retry: code === "TRANSIENT",
      delayMs: 1000,
    });
    const retry = f.calls.find((x) => x.sql.includes("next_attempt_at=CASE"));
    assert.equal(retry.args[0], code === "TRANSIENT" ? "pending" : "failed");
    assert.equal(
      f.calls.some((x) => x.sql.includes("phase='finished'")),
      code !== "TRANSIENT",
    );
  }
});
test("actual store page token invalidation queues newest-page restart within page cap", async () => {
  const f = dbFixture({
    w: {
      phase: "discovery",
      channel_id: "a",
      page_count: 1,
      status: "claimed",
      attempts: 1,
      dispatch_order: "1",
    },
  });
  await f.store.failed(f.lease, "synthetic-work", {
    code: "PAGE_TOKEN",
    retry: false,
    delayMs: 0,
  });
  const next = f.calls.find((x) =>
    x.sql.startsWith("INSERT INTO c1.collection_work")
  );
  assert.equal(next.args[8], null);
  assert.equal(next.args[10], 2);
});
test("actual store discovery commit queues the next round page and records candidates without per-page tasks", async () => {
  const p = {
    items: [{ contentDetails: { videoId: "new" } }],
    nextPageToken: "next",
  };
  const f = dbFixture({
    w: {
      phase: "discovery",
      channel_id: "a",
      page_count: 0,
      dispatch_order: "1",
      seen_tokens: [],
      selected_ids: [],
      status: "staged",
      staged_response: p,
      payload_hash: await hash(p),
      observed_at: "2026-10-17T20:44:00Z",
    },
  });
  await f.store.commit(f.lease, "synthetic-work");
  const inserts = f.calls.filter((x) =>
    x.sql.startsWith("INSERT INTO c1.collection_work")
  );
  assert.equal(inserts.length, 1);
  assert.equal(inserts[0].args[5], "discovery");
  assert.equal(inserts[0].args[8], "next");
  assert.equal(inserts[0].args[9], 4);
  const update = f.calls.find((x) => x.sql.includes("SET status='committed'"));
  assert.deepEqual(JSON.parse(update.args[1]).discovered, ["new"]);
});
test("reaching the admission cutoff completes a channel without another page", async () => {
  const p = {
    items: [{
      contentDetails: {
        videoId: "old",
        videoPublishedAt: "2026-08-01T00:00:00Z",
      },
    }],
    nextPageToken: "next",
  };
  const f = dbFixture({
    coord: { admission_published_after: new Date("2026-09-17T20:30:00Z") },
    w: {
      phase: "discovery",
      channel_id: "a",
      page_count: 0,
      dispatch_order: "1",
      seen_tokens: [],
      selected_ids: [],
      status: "staged",
      staged_response: p,
      payload_hash: await hash(p),
      observed_at: "2026-10-17T20:44:00Z",
    },
  });
  await f.store.commit(f.lease, "synthetic-work");
  assert.equal(
    f.calls.some((x) => x.sql.startsWith("INSERT INTO c1.collection_work")),
    false,
  );
  const outcome = JSON.parse(
    f.calls.find((x) => x.sql.includes("SET status='committed'")).args[1],
  );
  assert.equal(outcome.coverage, true);
  assert.equal(outcome.reached_cutoff, true);
  assert.deepEqual(outcome.discovered, []);
});
test("candidates are seeded once, across channels, in batches of 50 after discovery", async () => {
  let seeded = false;
  const page = (channel_id, ids) =>
    work({
      work_id: `page-${channel_id}`,
      phase: "discovery",
      channel_id,
      selected_ids: [],
      status: "committed",
      outcomes: { discovered: ids },
    });
  const a = Array.from({ length: 30 }, (_, i) => `a${i}`);
  const b = [...Array.from({ length: 30 }, (_, i) => `b${i}`), "a0"];
  const f = dbFixture({
    run: {
      summary: { rotation: 0, discoverySeeded: true, candidatesSeeded: false },
    },
    respond: (sql) => {
      if (sql.includes("FROM c1.collection_work WHERE run_id=$1 ORDER")) {
        return seeded
          ? [
            work({
              work_id: "cand-0",
              phase: "candidates",
              selected_ids: ["a1"],
            }),
          ]
          : [page("a", a), page("b", b)];
      }
      if (sql.startsWith("SELECT video_id FROM c1.videos WHERE video_id=ANY")) {
        return [{ video_id: "b5" }];
      }
      if (sql.startsWith("UPDATE c1.collection_runs SET summary=")) {
        seeded = true;
        return [];
      }
    },
  });
  const next = await f.store.next(f.lease);
  assert.equal(next.phase, "candidates");
  const inserts = f.calls.filter((x) =>
    x.sql.startsWith("INSERT INTO c1.collection_work")
  );
  assert.deepEqual(inserts.map((x) => x.args[5]), ["candidates", "candidates"]);
  assert.deepEqual(inserts.map((x) => x.args[6].length), [50, 9]);
  assert.deepEqual(inserts.map((x) => x.args[7]), [null, null]);
  const ids = inserts.flatMap((x) => x.args[6]);
  assert.equal(new Set(ids).size, 59);
  assert.equal(ids.includes("b5"), false);
});
test("repeated discovery tokens stop that channel without enqueueing another page", async () => {
  const p = { items: [], nextPageToken: "repeat" };
  const f = dbFixture({
    w: {
      phase: "discovery",
      channel_id: "a",
      page_count: 0,
      dispatch_order: "0",
      seen_tokens: ["repeat"],
      selected_ids: [],
      status: "staged",
      staged_response: p,
      payload_hash: await hash(p),
      observed_at: "2026-10-17T20:44:00Z",
    },
  });
  await f.store.commit(f.lease, "synthetic-work");
  assert.equal(
    f.calls.some((x) => x.sql.startsWith("INSERT INTO c1.collection_work")),
    false,
  );
  const update = f.calls.find((x) => x.sql.includes("SET status='committed'"));
  assert.equal(JSON.parse(update.args[1]).coverage, false);
});
test("candidate admission increments revision only after matching staged discovery ownership", async () => {
  const p = payload();
  const f = dbFixture({
    w: {
      phase: "candidates",
      status: "staged",
      staged_response: p,
      payload_hash: await hash(p),
      observed_at: "2026-10-17T20:44:00Z",
    },
    respond: (sql) =>
      sql.startsWith("SELECT video_id,channel_id")
        ? []
        : sql.startsWith("SELECT w.channel_id")
        ? [{ channel_id: "a", video_id: "v" }]
        : sql.includes("RETURNING inventory_revision")
        ? [{ inventory_revision: "2" }]
        : undefined,
  });
  await f.store.commit(f.lease, "synthetic-work");
  const sources = f.calls.find((x) => x.sql.startsWith("SELECT w.channel_id"));
  assert.ok(
    sources.sql.includes("jsonb_array_elements(w.staged_response->'items')"),
  );
  const admission = f.calls.find((x) =>
    x.sql.startsWith("INSERT INTO c1.videos")
  );
  assert.deepEqual(admission.args, ["v", "a", "2"]);
  const bad = payload({}, "b");
  const wrong = dbFixture({
    w: {
      phase: "candidates",
      status: "staged",
      staged_response: bad,
      payload_hash: await hash(bad),
      observed_at: "2026-10-17T20:44:00Z",
    },
    respond: (sql) =>
      sql.startsWith("SELECT w.channel_id")
        ? [{ channel_id: "a", video_id: "v" }]
        : undefined,
  });
  await wrong.store.commit(wrong.lease, "synthetic-work");
  assert.equal(
    wrong.calls.some((x) => x.sql.startsWith("INSERT INTO c1.videos")),
    false,
  );
});

class MemoryStore {
  constructor(tasks = [work()]) {
    this.tasks = tasks;
    this.calls = [];
    this.fence = 1;
    this.time = 0;
    this.expires = 75;
    this.reservations = 0;
    this.rows = new Map();
  }
  async claim() {
    if (this.owner && this.time < this.expires) return { state: "busy" };
    this.owner = `owner-${++this.fence}`;
    this.expires = this.time + 75;
    return { lease: { owner: this.owner, fence: this.fence } };
  }
  check(l) {
    if (
      l.owner !== this.owner || l.fence !== this.fence ||
      this.time >= this.expires
    ) throw new Stop("LEASE_LOST");
  }
  async next(l) {
    this.check(l);
    return this.tasks.find((w) =>
      w.status !== "committed" && w.status !== "failed"
    );
  }
  async reserve(l, id) {
    this.check(l);
    this.calls.push("reserve");
    this.reservations++;
    const w = this.tasks.find((w) => w.work_id === id);
    w.attempts++;
    return w;
  }
  async stage(l, id, p, t, h) {
    this.check(l);
    this.calls.push("stage");
    Object.assign(this.tasks.find((w) => w.work_id === id), {
      staged_response: p,
      observed_at: t,
      payload_hash: h,
    });
  }
  async commit(l, id) {
    this.check(l);
    this.calls.push("commit");
    const w = this.tasks.find((w) => w.work_id === id);
    const old = this.rows.get(id);
    await replayCheck(old?.hash, w.payload_hash);
    this.rows.set(id, { hash: w.payload_hash, time: w.observed_at });
    w.status = "committed";
  }
  async failed(l, id, error) {
    this.check(l);
    this.calls.push(error.code);
    this.tasks.find((w) => w.work_id === id).status = "failed";
  }
  async report(l) {
    this.check(l);
    return { state: "synthetic", attempts: this.reservations };
  }
  async release(l) {
    if (l.owner === this.owner && l.fence === this.fence) this.owner = null;
  }
}
const execute = (store, transport, other = {}) =>
  collect({
    store,
    transport,
    config: c,
    action: "daily-start",
    deadline: 60000,
    now: () => 0,
    ...other,
  });
test("orchestration reserves before dispatch, then stages and commits", async () => {
  const s = new MemoryStore();
  await execute(s, {
    request: async () => {
      assert.deepEqual(s.calls, ["reserve"]);
      return payload();
    },
  });
  assert.deepEqual(s.calls, ["reserve", "stage", "commit"]);
});
test("crash after staging resumes without another call/reservation and preserves observation", async () => {
  const w = work({
    staged_response: payload(),
    observed_at: "2026-10-17T20:44:00Z",
    payload_hash: await hash(payload()),
  });
  const s = new MemoryStore([w]);
  await execute(s, { request: () => assert.fail("API after staging") });
  assert.equal(s.reservations, 0);
  assert.equal(s.rows.get(w.work_id).time, w.observed_at);
});
test("crash after durable reservation consumes it, recovery needs another reservation", async () => {
  const s = new MemoryStore(), l = (await s.claim()).lease;
  await s.reserve(l, "synthetic-work");
  s.time = 76;
  await execute(s, { request: async () => payload() });
  assert.equal(s.reservations, 2);
});
test("concurrent claim busy until expiry; takeover invalidates old writer", async () => {
  const s = new MemoryStore(), a = (await s.claim()).lease;
  assert.equal((await s.claim()).state, "busy");
  s.time = 76;
  const b = (await s.claim()).lease;
  assert.ok(b.fence > a.fence);
  await assert.rejects(
    () => s.stage(a, "synthetic-work", payload(), "2026-10-17T20:44:00Z", "x"),
    /LEASE_LOST/,
  );
  await assert.rejects(() => s.commit(a, "synthetic-work"), /LEASE_LOST/);
});
test("handler deadline prevents dispatch; invocation has at most six attempts", async () => {
  const s = new MemoryStore();
  await execute(s, { request: () => assert.fail("deadline") }, {
    deadline: 14000,
  });
  assert.equal(s.reservations, 0);
  const many = new MemoryStore(
    Array.from({ length: 9 }, (_, i) => work({ work_id: `w${i}` })),
  );
  await execute(many, { request: async () => payload() });
  assert.equal(many.reservations, 6);
  assert.equal(LIMITS.attempts, 6);
  assert.equal(LIMITS.maxRunAttempts, 200);
});
test("transport errors are sanitized and fatal errors stop further dispatch", async () => {
  for (const code of ["API_AUTH", "QUOTA"]) {
    const s = new MemoryStore([work(), work({ work_id: "other" })]);
    await execute(s, {
      request: async () => {
        throw new YouTubeError(code);
      },
    });
    assert.equal(s.reservations, 1);
  }
});
test("transport has bounded response, fatal quota/auth and retryable 429/5xx", async () => {
  for (
    const [status, body, code, retry] of [
      [
        403,
        { error: { errors: [{ reason: "quotaExceeded" }] } },
        "QUOTA",
        false,
      ],
      [401, {}, "API_AUTH", false],
      [429, {}, "TRANSIENT", true],
      [503, {}, "TRANSIENT", true],
    ]
  ) {
    const t = createYouTube({
      apiKey: "synthetic",
      fetcher: async () => new Response(JSON.stringify(body), { status }),
    });
    await assert.rejects(
      () => t.request(work()),
      (e) => e.code === code && e.retry === retry,
    );
  }
  const huge = createYouTube({
    apiKey: "synthetic",
    fetcher: async () => new Response("x".repeat(196609)),
  });
  await assert.rejects(() => huge.request(work()), /BODY_LIMIT/);
});
test("transport uses fixed YouTube endpoints, filters fields, and never places key in URL", async () => {
  let url, options;
  const t = createYouTube({
    apiKey: "synthetic-secret",
    fetcher: async (u, o) => {
      url = u;
      options = o;
      return new Response('{"items":[]}');
    },
  });
  await t.request(work());
  assert.equal(url.origin, "https://www.googleapis.com");
  assert.equal(url.searchParams.get("key"), null);
  assert.equal(options.headers["X-Goog-Api-Key"], "synthetic-secret");
  assert.equal(options.redirect, "error");
  assert.match(url.searchParams.get("fields"), /contentDetails\/duration/);
  assert.match(url.searchParams.get("fields"), /categoryId/);
  await t.request(work({ phase: "channels", selected_ids: ["a"] }));
  assert.match(url.searchParams.get("part"), /topicDetails/);
  assert.match(url.searchParams.get("fields"), /country,defaultLanguage/);
  assert.match(url.searchParams.get("fields"), /topicDetails\/topicCategories/);
  await t.request(
    work({ phase: "discovery", playlist: "UUa", selected_ids: [] }),
  );
  assert.match(url.pathname, /playlistItems$/);
  assert.match(url.searchParams.get("fields"), /videoPublishedAt/);
  assert.equal(url.searchParams.has("q"), false);
});
test("phase reporting keeps inventory, discovery and candidates distinct", () => {
  const f = dbFixture();
  const summary = f.store.summary([
    work({ status: "committed" }),
    work({ phase: "discovery", channel_id: "a", status: "deferred" }),
    work({ phase: "candidates", status: "deferred" }),
  ]);
  assert.equal(summary.refresh_complete, true);
  assert.equal(summary.discovery_complete, false);
  assert.equal(summary.candidates_complete, false);
});
test("source guard: no forbidden credential reads, imports, SQL namespaces or cleanup", () => {
  for (
    const name of [
      "index.ts",
      "runtime.mjs",
      "driver.mjs",
      "core.mjs",
      "handler.mjs",
      "collector.mjs",
      "youtube.mjs",
      "store.mjs",
    ]
  ) {
    const source = readFileSync(
      new URL(
        `../../../supabase/functions/c1-collect/${name}`,
        import.meta.url,
      ),
      "utf8",
    );
    assert.doesNotMatch(
      source,
      /COMPONENT1_DB_URL|SUPABASE_DB_URL|SERVICE_ROLE|research\.|annotation\.|\.env["']|shared\//,
    );
    if (name === "store.mjs") {
      assert.doesNotMatch(
        source,
        /\bDELETE\b|\bTRUNCATE\b|SECURITY DEFINER|SET ROLE/,
      );
    }
  }
});

// Deno additionally verifies its sandbox permissions.
if (typeof Deno !== "undefined") {
  test("Deno validation denies live connections, secrets, writes and subprocesses", async () => {
    for (
      const permission of [
        { name: "net" },
        { name: "env" },
        { name: "write" },
        { name: "run" },
        { name: "ffi" },
        { name: "read", path: new URL("../../../.env", import.meta.url) },
      ]
    ) {
      assert.equal((await Deno.permissions.query(permission)).state, "denied");
    }
  });
}
