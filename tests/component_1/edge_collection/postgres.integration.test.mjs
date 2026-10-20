// NOT RE-VALIDATED: updated on 2026-10-20 for the entity-keyed schema
// (organizations, cohort_channels, holdout views) but not executed since.
// Explicit opt-in integration tests. They require a synthetic database URL supplied
// by the caller; they never read .env and do not provide a fallback URL.
import test, { after, before } from "node:test";
import assert from "node:assert/strict";
import { postgresFactory } from "../../../supabase/functions/c1-collect/driver.mjs";

const url = process.env.C1_IT_DB_URL;
const enabled = Boolean(url);
const c = {
  active: true,
  token: "synthetic-integration-token-".repeat(4),
  dbUrl: url ?? "postgres://invalid.invalid/disabled",
  apiKey: "synthetic-api-key",
  cohort: process.env.C1_IT_COHORT ?? "synthetic_c1_it",
  version: "test",
  manifest: "a".repeat(64),
  retention: "synthetic-integration-retention",
};

// Internal test seam only: next 02:30 Asia/Colombo instant.
const nextInWindow = () => {
  const now = Date.now();
  const shifted = new Date(now + 330 * 60000);
  const date = shifted.toISOString().slice(0, 10);
  let candidate = Date.parse(`${date}T02:30:00+05:30`);
  if (candidate <= now) candidate += 24 * 60 * 60 * 1000;
  return candidate;
};

const required = (name) => {
  const value = process.env[name];
  if (!value) throw new Error(`missing synthetic fixture variable: ${name}`);
  return value;
};

const makeStore = postgresFactory(
  () => import("postgres"),
  () => true,
  { scheduleClock: nextInWindow },
);
let store;
let acquiredLease;
let replayWorkId;

before(async () => {
  if (!enabled) return;
  store = await makeStore(c);
});

after(async () => {
  await store?.close();
});

function it(name, fn) {
  return test(name, { skip: !enabled }, fn);
}

// The fixture loader must create these rows using the c1_owner path before this
// file is run: organizations, the enabled cohort, channels with organization_id,
// matching cohort_channels rows and the coordination row. The test process
// itself connects only as c1_collector.
it("uses the actual driver and collector transaction identity", async () => {
  const result = await store.transaction(async (q) =>
    (await q("SELECT session_user,current_user"))[0]
  );
  assert.equal(result.session_user, "c1_collector");
  assert.equal(result.current_user, "c1_collector");
});

it("claims concurrently with one winner and reserves the API budget", async () => {
  const [a, b] = await Promise.all([
    store.claim(c, "daily-start"),
    store.claim(c, "daily-start"),
  ]);
  const results = [a, b];
  assert.equal(results.filter((x) => x.lease).length, 1);
  assert.equal(results.filter((x) => x.state === "busy").length, 1);
  const lease = results.find((x) => x.lease).lease;
  acquiredLease = lease;
  const work = await store.next(lease);
  assert.ok(work);
  replayWorkId = work.work_id;
  const reserved = await store.reserve(lease, work.work_id);
  assert.equal(reserved.status, "claimed");
  assert.equal(reserved.attempts, 1);
});

it("rolls back a failed transaction without leaving a staged write", async () => {
  const workId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  await assert.rejects(
    () =>
      store.transaction(async (q) => {
        await q(
          `INSERT INTO c1.collection_work
        (work_id,run_id,cohort_id,version,work_key,phase,selected_ids,dispatch_order,status)
        VALUES ($1,$2,$3,$4,$5,'refresh',ARRAY['synthetic-video'],99,'pending')`,
          [
            workId,
            acquiredLease.run,
            c.cohort,
            c.version,
            "rollback-probe",
          ],
        );
        await q("SELECT 1 / 0");
      }),
  );
  const rows = await store.transaction((q) =>
    q(
      "SELECT count(*)::integer AS n FROM c1.collection_work WHERE work_id=$1",
      [
        workId,
      ],
    )
  );
  assert.equal(rows[0].n, 0);
});

it("preserves identical replay and rejects conflicting replay", async () => {
  const workId = replayWorkId;
  const lease = acquiredLease;
  assert.ok(lease);
  const payload = { items: [] };
  const observed = "2026-10-18T00:01:00.000Z";
  const digest = await (async () => {
    const bytes = new TextEncoder().encode(JSON.stringify(payload));
    const hash = await crypto.subtle.digest("SHA-256", bytes);
    return [...new Uint8Array(hash)].map((x) => x.toString(16).padStart(2, "0"))
      .join("");
  })();
  await store.stage(lease, workId, payload, observed, digest);
  await store.stage(lease, workId, payload, observed, digest);
  await assert.rejects(
    () =>
      store.stage(lease, workId, payload, "2026-10-18T00:01:01.000Z", digest),
    /REPLAY_CONFLICT/,
  );
});

it("rejects stale workers after takeover and preserves the fencing check", async () => {
  const stale = {
    run: required("C1_IT_STALE_RUN_ID"),
    owner: required("C1_IT_STALE_OWNER"),
    fence: required("C1_IT_STALE_FENCE"),
  };
  await assert.rejects(
    () => store.reserve(stale, required("C1_IT_STALE_WORK_ID")),
    /LEASE_LOST|RUN_CLOSED/,
  );
  await assert.rejects(
    () => store.report(stale),
    /LEASE_LOST/,
  );
});

it("enforces collector permissions and RLS for synthetic out-of-scope rows", async () => {
  await assert.rejects(
    () =>
      store.transaction((q) => q("SELECT * FROM research.c1_synthetic_probe")),
    /permission denied|does not exist/i,
  );
  await assert.rejects(
    () => store.transaction((q) => q("SET ROLE c1_owner")),
    /permission denied|cannot set role/i,
  );
  // Model views belong to c1_model_reader only; the collector cannot read them.
  await assert.rejects(
    () => store.transaction((q) => q("SELECT * FROM c1.training_observations")),
    /permission denied/i,
  );
});

it("cannot add channels, change memberships or change the holdout flag", async () => {
  for (
    const sql of [
      "INSERT INTO c1.channels (channel_id,organization_id,admitted_at,admission_source) VALUES ('x','x',now(),'x')",
      "UPDATE c1.cohort_channels SET role='competitor'",
      "UPDATE c1.organizations SET is_holdout=false",
    ]
  ) {
    await assert.rejects(
      () => store.transaction((q) => q(sql)),
      /permission denied/i,
    );
  }
});
