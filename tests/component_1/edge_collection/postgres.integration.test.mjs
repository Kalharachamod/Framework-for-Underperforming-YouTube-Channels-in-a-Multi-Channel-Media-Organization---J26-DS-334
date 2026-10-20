// Explicit opt-in integration tests against a disposable local PostgreSQL. They
// use the real npm:postgres driver (driver.mjs), PostgresStore, collect() and the
// HTTP handler, connected only as c1_collector. YouTube is always mocked through
// the injected fetcher; the Deno permission set allows no other network access.
// The caller supplies the synthetic URL; .env is never read and there is no
// fallback. See POSTGRES_INTEGRATION_RUNBOOK.md for setup and the two phases:
//   C1_IT_PHASE=pending  the bootstrapped cohort is still pending/disabled
//   C1_IT_PHASE=enabled  the operator approved and enabled it in the container
import test, { after, before } from "node:test";
import assert from "node:assert/strict";
import { postgresFactory } from "../../../supabase/functions/c1-collect/driver.mjs";
import { createHandler } from "../../../supabase/functions/c1-collect/handler.mjs";
import { collect } from "../../../supabase/functions/c1-collect/collector.mjs";
import { createYouTube } from "../../../supabase/functions/c1-collect/youtube.mjs";
import {
  hash,
  schedule,
} from "../../../supabase/functions/c1-collect/core.mjs";

const url = process.env.C1_IT_DB_URL;
const phase = process.env.C1_IT_PHASE;
const c = {
  active: true,
  token: "synthetic-integration-token-".repeat(4),
  dbUrl: url ?? "postgres://invalid.invalid/disabled",
  apiKey: "synthetic-api-key",
  cohort: process.env.C1_IT_COHORT ?? "component_1_derana_vs_cm",
  version: process.env.C1_IT_VERSION ?? "0.3.0",
  manifest: process.env.C1_IT_MANIFEST_HASH ??
    "945cecc929247adfeda0d8c9bd4d512f0cc471990d492ee7a81a73efd0b0a1bb",
  retention: process.env.C1_IT_RETENTION ?? "synthetic-integration-retention",
};

// Internal test seam only: next 02:30 Asia/Colombo instant. Leases, deadlines
// and every mutation still use the database clock.
const nextInWindow = () => {
  const now = Date.now();
  const shifted = new Date(now + 330 * 60000);
  const date = shifted.toISOString().slice(0, 10);
  let candidate = Date.parse(`${date}T02:30:00+05:30`);
  if (candidate <= now) candidate += 24 * 60 * 60 * 1000;
  return candidate;
};
const windowStart = schedule(nextInWindow()).start;
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Two of these channels are Derana (training), one is Capital Maharaja (holdout).
const VIDEO_CHANNELS = [
  "UCCK3OZi788Ok44K97WAhLKQ",
  "UCRDDfbYPHX_GUJ4lcQYTc8A",
  "UCn0XmAUFv6d2tofMFEesSNw",
];
// Mocked YouTube Data API. The first playlistItems call fails once with 503 so
// the run exercises a persisted transient retry.
const calls = { channels: 0, playlistItems: 0, videos: 0 };
const fetcher = (requestUrl, init) => {
  assert.equal(requestUrl.host, "www.googleapis.com");
  assert.equal(init.headers["X-Goog-Api-Key"], c.apiKey);
  const endpoint = requestUrl.pathname.split("/").pop();
  calls[endpoint]++;
  const json = (status, body) =>
    Promise.resolve(
      new Response(JSON.stringify(body), {
        status,
        headers: { "content-type": "application/json" },
      }),
    );
  const published = new Date(Date.parse(windowStart) - 2 * 86400000)
    .toISOString();
  const ids = requestUrl.searchParams.get("id")?.split(",") ?? [];
  if (endpoint === "channels") {
    return json(200, {
      items: ids.map((id) => ({
        id,
        snippet: {
          title: `Synthetic ${id}`,
          publishedAt: "2015-01-01T00:00:00Z",
          country: "LK",
          defaultLanguage: "si",
        },
        statistics: {
          subscriberCount: "1000",
          viewCount: "50000",
          videoCount: "10",
        },
        contentDetails: { relatedPlaylists: { uploads: `UU${id.slice(2)}` } },
        topicDetails: {
          topicCategories: ["https://en.wikipedia.org/wiki/Television"],
        },
      })),
    });
  }
  if (endpoint === "playlistItems") {
    if (calls.playlistItems === 1) {
      return json(503, { error: { errors: [{ reason: "backendError" }] } });
    }
    const channel = `UC${requestUrl.searchParams.get("playlistId").slice(2)}`;
    const i = VIDEO_CHANNELS.indexOf(channel);
    return json(200, {
      items: i < 0 ? [] : [0, 1].map((k) => ({
        contentDetails: {
          videoId: `vid_${i}_${k}`,
          videoPublishedAt: published,
        },
        snippet: { channelId: channel },
      })),
    });
  }
  return json(200, {
    items: ids.map((id) => ({
      id,
      snippet: {
        channelId: VIDEO_CHANNELS[Number(id.split("_")[1])],
        title: `Synthetic ${id}`,
        publishedAt: published,
        categoryId: "24",
      },
      statistics: { viewCount: "100", likeCount: "5", commentCount: "1" },
      contentDetails: { duration: "PT3M20S" },
    })),
  });
};
const transport = createYouTube({ apiKey: c.apiKey, fetcher });
const makeStore = postgresFactory(
  () => import("postgres"),
  () => true,
  { scheduleClock: nextInWindow },
);

let store, second;
// Ungated read on the same c1_collector login (no identity/gate wrapper), so
// state can be inspected even while the gate is closed.
const raw = (sql, values = []) => store.db.transaction((q) => q(sql, values));
const counts = async () =>
  (await raw(`SELECT
    (SELECT count(*)::integer FROM c1.collection_runs) AS runs,
    (SELECT count(*)::integer FROM c1.collection_work) AS work,
    (SELECT count(*)::integer FROM c1.videos) AS videos,
    (SELECT count(*)::integer FROM c1.channel_stats_history) AS channel_history,
    (SELECT count(DISTINCT (channel_id, run_id))::integer FROM c1.channel_stats_history) AS channel_keys,
    (SELECT count(*)::integer FROM c1.video_stats_history) AS video_history,
    (SELECT count(DISTINCT (video_id, run_id))::integer FROM c1.video_stats_history) AS video_keys,
    (SELECT count(*)::integer FROM c1.channels WHERE metadata_observed_at IS NOT NULL) AS channels_observed,
    (SELECT fence::text FROM c1.collection_coordination) AS fence,
    (SELECT active_run_id::text FROM c1.collection_coordination) AS active_run,
    (SELECT admission_published_after FROM c1.collection_coordination) AS cutoff,
    (SELECT inventory_revision::text FROM c1.collection_coordination) AS revision`))[
    0
  ];

before(async () => {
  if (!url) return;
  store = await makeStore(c);
  second = await makeStore(c);
});
after(async () => {
  await store?.close();
  await second?.close();
});
const it = (when, name, fn) =>
  test(`[${when}] ${name}`, { skip: !url || phase !== when }, fn);

for (const when of ["pending", "enabled"]) {
  it(when, "connects through the real driver as c1_collector", async () => {
    const [identity] = await raw("SELECT session_user, current_user");
    assert.equal(identity.session_user, "c1_collector");
    assert.equal(identity.current_user, "c1_collector");
  });
}

it(
  "pending",
  "handler returns GATE_CLOSED in-window, with no API call and no writes",
  async () => {
    const before = await counts();
    assert.equal(before.runs, 0);
    assert.equal(before.fence, "0");
    assert.equal(before.cutoff, null);
    const env = {
      C1_ACTIVATED: "true",
      C1_CRON_TOKEN: c.token,
      C1_COLLECTOR_DB_URL: c.dbUrl,
      C1_YOUTUBE_API_KEY: c.apiKey,
      C1_COHORT_ID: c.cohort,
      C1_COHORT_VERSION: c.version,
      C1_MANIFEST_HASH: c.manifest,
      C1_RETENTION_DECISION_REFERENCE: c.retention,
    };
    const handler = createHandler({
      get: (k) => env[k],
      openStore: makeStore,
      createTransport: () => transport,
      collect,
    });
    for (const action of ["daily-start", "continuation"]) {
      const res = await handler(
        new Request("https://synthetic.invalid/c1-collect", {
          method: "POST",
          headers: {
            authorization: `Bearer ${c.token}`,
            "content-type": "application/json",
          },
          body: JSON.stringify({ action }),
        }),
      );
      assert.equal(res.status, 503);
      assert.deepEqual(await res.json(), { code: "GATE_CLOSED" });
    }
    assert.deepEqual(calls, { channels: 0, playlistItems: 0, videos: 0 });
    assert.deepEqual(await counts(), before);
  },
);

let lease, stagedWork;
it(
  "enabled",
  "concurrent claims on two connections give one lease and one busy",
  async () => {
    const results = await Promise.all([
      store.claim(c, "daily-start"),
      second.claim(c, "daily-start"),
    ]);
    assert.equal(results.filter((x) => x.lease).length, 1);
    assert.deepEqual(results.filter((x) => !x.lease), [{ state: "busy" }]);
    lease = results.find((x) => x.lease).lease;
    const state = await counts();
    assert.equal(state.runs, 1);
    assert.equal(state.active_run, lease.run);
    assert.equal(
      new Date(state.cutoff).toISOString(),
      new Date(Date.parse(windowStart) - 30 * 86400000).toISOString(),
    );
  },
);

it(
  "enabled",
  "a failed transaction rolls back without leaving a write",
  async () => {
    const workId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
    await assert.rejects(() =>
      store.transaction(async (q) => {
        await q(
          `INSERT INTO c1.collection_work
        (work_id,run_id,cohort_id,version,work_key,phase,selected_ids,dispatch_order,status)
        VALUES ($1,$2,$3,$4,'rollback-probe','refresh',ARRAY['synthetic-video'],99,'pending')`,
          [workId, lease.run, c.cohort, c.version],
        );
        await q("SELECT 1 / 0");
      })
    );
    const [row] = await raw(
      "SELECT count(*)::integer AS n FROM c1.collection_work WHERE work_id=$1",
      [workId],
    );
    assert.equal(row.n, 0);
  },
);

it(
  "enabled",
  "crash after staging: takeover commits the staged response once; stale worker rejected",
  async () => {
    const work = await store.next(lease);
    assert.equal(work.phase, "channels");
    const ready = await store.reserve(lease, work.work_id);
    assert.equal(ready.status, "claimed");
    const payload = await transport.request(ready);
    const observed = new Date().toISOString();
    const digest = await hash(payload);
    await store.stage(lease, work.work_id, payload, observed, digest);
    // Identical replay is a no-op; a different observation time is a conflict.
    await store.stage(lease, work.work_id, payload, observed, digest);
    await assert.rejects(
      () =>
        store.stage(
          lease,
          work.work_id,
          payload,
          new Date(Date.parse(observed) + 1000).toISOString(),
          digest,
        ),
      /REPLAY_CONFLICT/,
    );
    stagedWork = work.work_id;
    // Simulated crash: the worker drops its lease without committing.
    await store.release(lease);
    assert.equal((await counts()).channel_history, 0);
    const result = await collect({
      store,
      transport,
      config: c,
      action: "continuation",
      deadline: Date.now() + 60000,
    });
    assert.equal(result.state, "running");
    const state = await counts();
    assert.equal(state.channel_history, 41);
    assert.equal(state.channel_keys, 41);
    assert.equal(state.channels_observed, 41);
    assert.equal(calls.channels, 1);
    // The old worker's lease and fence are no longer valid.
    for (
      const attempt of [
        () => store.commit(lease, stagedWork),
        () => store.stage(lease, stagedWork, payload, observed, digest),
        () => store.reserve(lease, stagedWork),
        () => store.report(lease),
      ]
    ) await assert.rejects(attempt, /LEASE_LOST/);
  },
);

it(
  "enabled",
  "continuations finish the mocked run, including one transient retry",
  async () => {
    let result;
    for (let i = 0; i < 30; i++) {
      result = await collect({
        store,
        transport,
        config: c,
        action: "continuation",
        deadline: Date.now() + 60000,
      });
      if (result.state !== "running") break;
      await sleep(1200);
    }
    assert.equal(result.state, "complete");
    assert.equal(result.discovery_complete, true);
    assert.equal(result.candidates_complete, true);
    assert.deepEqual(calls, { channels: 1, playlistItems: 42, videos: 1 });
    const [run] = await raw(
      `SELECT status, attempts_reserved, discovery_attempts, inventory_complete,
      discovery_complete FROM c1.collection_runs WHERE run_id=$1`,
      [lease.run],
    );
    assert.deepEqual(run, {
      status: "complete",
      attempts_reserved: 44,
      discovery_attempts: 42,
      inventory_complete: true,
      discovery_complete: true,
    });
  },
);

it(
  "enabled",
  "snapshots and metadata were written once per entity",
  async () => {
    const state = await counts();
    assert.equal(state.channel_history, 41);
    assert.equal(state.channel_keys, 41);
    assert.equal(state.videos, 6);
    assert.equal(state.video_history, 6);
    assert.equal(state.video_keys, 6);
    assert.equal(state.revision, "6");
    const [video] = await raw(
      `SELECT v.channel_id, v.duration_seconds::integer AS duration, v.category_id,
      h.view_count::text AS views, h.like_count::text AS likes
    FROM c1.videos v JOIN c1.video_stats_history h USING (video_id)
    WHERE v.video_id='vid_2_1'`,
    );
    assert.deepEqual(video, {
      channel_id: VIDEO_CHANNELS[2],
      duration: 200,
      category_id: "24",
      views: "100",
      likes: "5",
    });
    const [channel] = await raw(
      `SELECT uploads_playlist_id, country, default_language, topic_categories
    FROM c1.channels WHERE channel_id=$1`,
      [VIDEO_CHANNELS[0]],
    );
    assert.deepEqual(channel, {
      uploads_playlist_id: `UU${VIDEO_CHANNELS[0].slice(2)}`,
      country: "LK",
      default_language: "si",
      topic_categories: ["https://en.wikipedia.org/wiki/Television"],
    });
  },
);

it(
  "enabled",
  "retrying after completion makes no API call and writes nothing",
  async () => {
    const before = await counts();
    const seen = { ...calls };
    for (
      const [action, state] of [
        ["daily-start", "already_finished"],
        ["continuation", "no_active_run"],
      ]
    ) {
      const result = await collect({
        store,
        transport,
        config: c,
        action,
        deadline: Date.now() + 60000,
      });
      assert.deepEqual(result, { state });
    }
    assert.deepEqual(calls, seen);
    assert.deepEqual(await counts(), before);
  },
);

it(
  "enabled",
  "history UPDATE, DELETE and TRUNCATE are denied, even with the purge setting",
  async () => {
    for (
      const sql of [
        "UPDATE c1.channel_stats_history SET view_count = 0",
        "DELETE FROM c1.channel_stats_history",
        "TRUNCATE c1.channel_stats_history",
        "UPDATE c1.video_stats_history SET view_count = 0",
        "DELETE FROM c1.video_stats_history",
        "TRUNCATE c1.video_stats_history",
      ]
    ) {
      await assert.rejects(
        () => store.transaction((q) => q(sql)),
        /permission denied/i,
      );
    }
    await assert.rejects(
      () =>
        store.transaction(async (q) => {
          await q("SET LOCAL c1.retention_purge = 'on'");
          await q("DELETE FROM c1.video_stats_history");
        }),
      /permission denied/i,
    );
    const state = await counts();
    assert.equal(state.channel_history, 41);
    assert.equal(state.video_history, 6);
  },
);

it("enabled", "collector permissions and isolation", async () => {
  for (
    const [sql, error] of [
      ["SELECT * FROM research.c1_synthetic_probe", /permission denied/i],
      ["SET ROLE c1_owner", /permission denied/i],
      ["SELECT * FROM c1.training_observations", /permission denied/i],
      ["SELECT * FROM c1.evaluation_observations", /permission denied/i],
      [
        "INSERT INTO c1.channels (channel_id,organization_id,admitted_at,admission_source) VALUES ('x','derana',now(),'x')",
        /permission denied/i,
      ],
      ["UPDATE c1.cohort_channels SET role='competitor'", /permission denied/i],
      ["UPDATE c1.organizations SET is_holdout=false", /permission denied/i],
      [
        "UPDATE c1.cohorts SET enabled=false",
        /permission denied/i,
      ],
    ]
  ) {
    await assert.rejects(() => store.transaction((q) => q(sql)), error, sql);
  }
});
