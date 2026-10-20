# C1 database definitions — review only

No SQL in this directory has been executed against Supabase. The 2026-10-20
schema (entity-keyed channels/videos/history, organizations, cohort membership,
holdout views) has only been checked as text; `LOCAL_VALIDATION_2026-10-18.md`
records a disposable-database run of the previous schema and does not cover it.
Existing research/annotation objects, roles, ACLs and migration tracking are
outside scope; no script reads or writes them.

## Run order (you run each file yourself in the Supabase SQL Editor)

| Step | File | What it does |
|---|---|---|
| 0 | `000_preflight_readonly.sql` | One read-only SELECT: server version, which GRANT form step 3 needs, your session/current user, whether C1 roles or schema already exist. Stop if any C1 object exists or the version is below 15. |
| 1 | `002a_roles.sql` | Creates `c1_owner` (NOLOGIN, will own the schema) and `c1_collector` (LOGIN, Edge collector). Fails if either exists. No passwords. |
| 2 | `002a2_model_reader_role.sql` | Creates `c1_model_reader` (LOGIN), the only login model code uses. No grants here. |
| 3 | `002a1_owner_membership.sql` | Lets `postgres` act as `c1_owner` (`SET ROLE`, no inheritance on PG16+). Keep exactly one GRANT form uncommented, chosen from step 0. |
| 4 | `001_schema.sql` | One transaction: schema `c1` owned by `c1_owner`, 11 tables, integrity triggers, the two model views, PUBLIC revokes. Fails if `c1` exists. |
| 5 | `002b_access.sql` | Collector grants, RLS on all 11 tables and write policies; reader grants on the two views; then a separate CONNECT grant for both logins. |
| 6 | `004_bootstrap_v0_3_0.sql` | One transaction as `c1_owner`: 2 organizations, the pending/disabled cohort, 41 channels, 41 memberships with roles, the coordination row. Self-checks counts and rolls back on any mismatch. No videos. |
| — | (outside SQL files) | Set passwords for `c1_collector` and `c1_model_reader` through the platform; later approve/enable the cohort as `c1_owner`. |
| 7 | `003_verify_readonly.sql` | Read-only catalog audit, designed to run as `c1_collector`. The SQL Editor shows only the last result and runs as `postgres`, so run it from a session logged in as `c1_collector` for meaningful results. |
| 8 | `005_revoke_owner_membership.sql` (optional) | Removes `postgres`'s ability to act as `c1_owner` once approval/enable is done. Re-grant with step 3 before any later C1 migration, bootstrap or approval change. |

## Data model

- `c1.organizations`: `organization_id`, `name`, `country`, `is_holdout`
  (no default; locked after insert by `guard_organization`).
- `c1.channels`: one row per channel, keyed by `channel_id`, with a required
  `organization_id`. Metadata includes `country`, `default_language`,
  `topic_categories`. `channel_id`, `organization_id` and admission fields are
  locked by `guard_inventory`.
- `c1.cohort_channels`: `(cohort_id, version, channel_id, role)`, role one of
  `owned`, `competitor`, `generalization_test`. Rows are immutable and must be
  in the cohort's `channel_ids` (`guard_membership`).
- `c1.videos`: one row per video, keyed by `video_id`, with a locked owning
  `channel_id`; metadata adds `duration_seconds` and `category_id`.
- `c1.channel_stats_history` PK `(channel_id, observed_at)` and
  `c1.video_stats_history` PK `(video_id, observed_at)`. `cohort_id`, `version`,
  `run_id` and `work_id` are required provenance, not key columns, so adding
  channels or a new cohort version never splits a series. Each run observes an
  entity at most once (`UNIQUE (entity, run_id)`).
- `c1.collection_coordination.admission_published_after` is set once by the first
  run (scheduled time minus `cohorts.admission_lookback_days`, 30) and then locked.
- Views `c1.training_observations` (`WHERE o.is_holdout = false`) and
  `c1.evaluation_observations` (`WHERE o.is_holdout = true`) have identical
  bodies otherwise. Both are `security_barrier = true, security_invoker = false`
  and owned by `c1_owner`, so `c1_model_reader` reads through them without any
  base-table privilege and cannot bypass the holdout filter.

## Security that is unchanged

Separate owner and runtime roles, no SECURITY DEFINER, invoker triggers with a
fixed catalog search path, PUBLIC revoked on all C1 tables, views and functions,
column-level UPDATE grants only, no DELETE/TRUNCATE grants, history append-only
for every role (`guard_history` blocks UPDATE/TRUNCATE; DELETE only inside a
retention purge with `SET LOCAL c1.retention_purge = 'on'`; see the design doc),
staged responses immutable, every collector INSERT/UPDATE gated by RLS on an
approved and enabled cohort. Entity rows (channels, videos) pass the gate when
their channel belongs to such a cohort; history rows additionally require their
provenance cohort to be that cohort. The collector can no longer insert channels:
only the reviewed bootstrap adds them. Object owners remain trusted and RLS is
not forced on the owner, which the bootstrap relies on.

## Manifest hash

`cohorts.manifest_hash` is the SHA-256 of the manifest's canonical JSON (parsed,
keys sorted, `,`/`:` separators without spaces, non-ASCII kept, UTF-8), exactly
as described in the manifest's `manifest_hash_method`. Raw file bytes are not
hashed. Any manifest edit changes the hash; regenerate `004` and rerun
`tests/component_1/test_c1_cohort_v030.py`.

## Offline checks (no SQL execution, DB, network or environment files)

```powershell
.venv/Scripts/python.exe -I -B tests/component_1/test_c1_sql_static.py
.venv/Scripts/python.exe -I -B tests/component_1/test_c1_cohort_v030.py
```

These text assertions detect selected regressions only. They do not parse or
execute PostgreSQL and cannot establish syntax correctness, privilege isolation,
RLS/trigger semantics, race safety or live compatibility. Before production,
run the scripts once in a throwaway database (for example a Supabase branch) and
the not-re-validated `tests/component_1/test_c1_postgres_local.ps1` there.

## Limits that remain

- Lease/fence verification, budget reservation, work transitions, refresh-due
  selection, replay hash comparison and completion are collector transaction
  logic; column grants do not prove those algorithms.
- Staged responses are capped at 256 KiB and outcomes at 64 KiB per task; staged
  response removal/retention is deliberately absent pending an approved policy.
- Existing PUBLIC or inherited privileges, callable privileged routines and views
  can defeat isolation; the local report found PUBLIC TEMP, which still needs a
  decision. Do not change shared/PUBLIC privileges as a workaround.
- A restricted DB login does not remove privileged credentials injected into the
  Edge environment. See the design's environment-isolation limitation.
