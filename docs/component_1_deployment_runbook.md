# C1 deployment runbook — 41-channel Derana vs Capital Maharaja cohort

Status: preparation only. Activation and scheduling remain disabled. None of the SQL, secret, deployment or scheduler actions below were executed while preparing this runbook. Revised 2026-10-20; the previous 43-channel (`component_1_audited43` 0.2.0-proposed) plan is superseded.

## Inputs

- Manifest: `config/cohorts/component_1_derana_vs_cm_v0.3.0.proposed.json` (41 channels: 18 Derana `owned`, 23 Capital Maharaja `competitor`; Capital Maharaja `is_holdout=true`). Status `proposed`, `enabled=false`, not selected for collection. The 2026-10-19 approval reported for the 43-channel cohort does not carry over.
- SQL, in this order (details in `research/component_1/sql/README.md`): `000_preflight_readonly.sql`, `002a_roles.sql`, `002a2_model_reader_role.sql`, `002a1_owner_membership.sql`, `001_schema.sql`, `002b_access.sql`, `004_bootstrap_v0_3_0.sql`, then `003_verify_readonly.sql`; optional `005_revoke_owner_membership.sql` after approval.
- Edge Function: the complete `supabase/functions/c1-collect/` directory.
- Evidence (see "Validation status" in `docs/component_1_collection_design.md`): offline tests; this SQL run in Supabase order on disposable local PostgreSQL 17.11 as a Supabase-like non-superuser `postgres`; and a collector integration run with the real driver as `c1_collector` over TLS with YouTube mocked (`tests/component_1/edge_collection/POSTGRES_INTEGRATION_RUNBOOK.md`). `LOCAL_VALIDATION_2026-10-18.md` covers the previous schema only.

## 0. Read-only preflight

Run `000_preflight_readonly.sql` in the SQL Editor. It returns one row. Continue only if: `server_version_num` is at least 150000, `existing_c1_roles_expected_null` is NULL, `c1_schema_exists_expected_false` is false, and `current_user_can_create_schema` and `current_user_can_create_roles` are true. Note which GRANT form `grant_form_for_002a1` names. Any existing C1 object is a stop-and-review condition; do not reuse, drop or repair it.

## 1. Roles

Run `002a_roles.sql` (creates `c1_owner`, `c1_collector`), then `002a2_model_reader_role.sql` (creates `c1_model_reader`). Each fails if a role exists. No passwords are set.

## 2. Owner membership for postgres

Edit `002a1_owner_membership.sql` so exactly one GRANT form is active (PG16+ form by default; PG15 form commented), then run it. This lets `postgres` create the schema for `c1_owner` and `SET ROLE c1_owner` in later steps.

## 3. Schema

Run `001_schema.sql`. One transaction creates schema `c1` (owner `c1_owner`), 11 tables, triggers, and the views `training_observations` and `evaluation_observations`. Any error rolls everything back; do not edit the SQL to work around a collision.

## 4. Access

Run `002b_access.sql`: collector grants, RLS on all 11 tables and write policies, reader grants on the two views, then a separate CONNECT grant for `c1_collector` and `c1_model_reader`. Stop on any error.

## 5. Bootstrap

Run `004_bootstrap_v0_3_0.sql`. It inserts 2 organizations, the cohort `component_1_derana_vs_cm` / `0.3.0` (pending, disabled, budgets 200/70/20, 10 pages, 30-day lookback), 41 channels, 41 memberships and the coordination row. Its built-in check raises `C1 bootstrap verification failed` and rolls back on any mismatch, and otherwise reports `C1 bootstrap OK: ...` as a notice. No videos are inserted and nothing is read from other schemas.

## 6. Passwords and Edge settings (outside SQL)

Set passwords for `c1_collector` and `c1_model_reader` through the platform; never in SQL files, manifests, shell history or URLs in the repository. Edge settings, supplied only by the authorized operator:

- `C1_ACTIVATED` — leave unset/false until activation is separately approved.
- `C1_CRON_TOKEN` — C1-only high-entropy bearer token.
- `C1_COLLECTOR_DB_URL` — recommended: the Supabase transaction pooler, `postgresql://c1_collector.<project ref>:<url-encoded password>@<region>.pooler.supabase.com:6543/postgres?sslmode=require`. The code accepts only the user `c1_collector` or exactly `c1_collector.<20-char lowercase project ref>`, `sslmode=require` or `verify-full`, and no other URL options; the pooler strips the ref, and every store transaction checks that `session_user` and `current_user` are `c1_collector`. The store uses only transaction-scoped settings and no prepared statements, so transaction mode is compatible (the session pooler on 5432 also works). The driver always verifies the server certificate against the runtime trust store; whether the pooler chain passes is checked by the first activated call returning `GATE_CLOSED` rather than `INTERNAL`.
- `C1_YOUTUBE_API_KEY` — dedicated collection key.
- `C1_COHORT_ID=component_1_derana_vs_cm`, `C1_COHORT_VERSION=0.3.0`.
- `C1_MANIFEST_HASH` — the canonical-JSON hash embedded in `004` (recompute with `tests/component_1/test_c1_cohort_v030.py`; method in the manifest's `manifest_hash_method`).
- `C1_RETENTION_DECISION_REFERENCE` — required before real persistence; no value is invented here.

## 7. Verify

Run `003_verify_readonly.sql` from a session logged in as `c1_collector`; the SQL Editor runs as `postgres` and shows only the last result. Confirm the collector cannot insert channels or memberships, cannot read the model views, and that the views are owned by `c1_owner` with `security_barrier=true`. Confirm `c1_model_reader` can read only the two views.

## 8. Approval, first run and cron — future, still gated

Approve and enable the cohort as `c1_owner` (fill `approved_by`, `approved_at`, `approval_reference`, `retention_decision_reference`, then `enabled=true`) only after cohort approval, retention, monitoring owner and the privilege audit are settled. Optionally run `005_revoke_owner_membership.sql` afterwards; re-grant with `002a1` before any later C1 change.

The first `daily-start` inside the 02:00–03:00 Asia/Colombo window sets the 30-day admission cutoff and seeds videos through discovery. Schedule a daily start plus continuation every minute in that window (6 dispatches per invocation, at most 360 per window). Measure uploads per day in the first week against the quota table in the design doc; above about 85 uploads/day discovery becomes partial. Do not create or enable cron jobs until separately approved.

## Current blockers

Cohort approval for v0.3.0, retention decision/reference, monitoring owner, live privilege/isolation preflight (including PUBLIC TEMP), passwords/secrets, verification of the 5 lower-confidence Capital Maharaja channels, and a first deployed check that the Edge runtime reaches the pooler with certificate verification (expect `GATE_CLOSED` while the cohort is pending).
