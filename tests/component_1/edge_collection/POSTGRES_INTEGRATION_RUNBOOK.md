# C1 PostgreSQL integration-test preparation

**NOT RE-VALIDATED.** On 2026-10-20 the schema changed to entity-keyed channels,
videos and history, with `c1.organizations`, `c1.cohort_channels`, the holdout
views and the `c1_model_reader` role. `postgres.integration.test.mjs` and
`../test_c1_postgres_local.ps1` were updated to match but have not been executed
since. Apply order for a disposable database: `002a_roles.sql`,
`002a2_model_reader_role.sql`, `001_schema.sql`, `002b_access.sql` (a superuser
fixture login does not need `002a1`). The fixture loader must now also create
organizations (one with `is_holdout=true`), channels with `organization_id`, and
`cohort_channels` rows with roles.

This is a future, explicitly authorized step. The test file uses the actual
`npm:postgres@3.4.7` driver through `postgresFactory` and the actual
`PostgresStore`; it does not use the mocked query adapter in
`collection.test.mjs`. It is opt-in and skips unless `C1_IT_DB_URL` is supplied.

## Current state and prerequisites

- The named container currently exists but is stopped (`Exited (255)`), with
  PostgreSQL 17.11, `network none`, no published ports, no bind mounts, and
  tmpfs at `/var/lib/postgresql/data`, `/var/run/postgresql`, and `/tmp`. Its
  previous database state is therefore not available for testing and must not be
  assumed to have survived. Starting it is a future container change, not part
  of this preparation.
- The reviewed SQL must already be applied in the disposable database. Do not
  reapply it through this test.
- A synthetic fixture-loader path using `c1_owner` must create an enabled
  synthetic cohort, matching channels, videos, coordination row, and uniquely
  identifiable run/work rows. The collector test process must use only the
  `c1_collector` login. Fixture setup must be idempotent or use a fresh
  database; the existing PowerShell fixture is intentionally non-repeatable.
- Deno 2.9.7 and a runtime inside the isolated execution environment.
- The pinned `npm:postgres@3.4.7` package, its transitive graph, and a reviewed
  Deno lockfile. There is currently no C1 lockfile and the visible default Deno
  npm cache has no PostgreSQL package files. Required future downloads are the
  npm registry metadata and package graph for `postgres@3.4.7`, subject to
  supply-chain review. No download has been performed.
- A synthetic administrator fixture loader, run separately as `c1_owner`, that
  creates the enabled cohort, channels, videos, coordination row, active run,
  refresh work row, and an expired-lease run/work row. It must export:
  `C1_IT_REPLAY_WORK_ID`, `C1_IT_STALE_RUN_ID`, `C1_IT_STALE_OWNER`,
  `C1_IT_STALE_FENCE`, and `C1_IT_STALE_WORK_ID`. It must also create synthetic
  `research.c1_synthetic_probe` for the permission assertion. The test process
  never uses `c1_owner`.
- A local TLS configuration: PostgreSQL server certificate/key and a synthetic
  CA certificate configured inside the database runtime; the certificate must
  validate for the hostname used by `C1_IT_DB_URL`. The Deno process must
  receive that CA through the approved Node/Deno trust configuration (for
  example, `NODE_EXTRA_CA_CERTS`), without weakening `rejectUnauthorized: true`
  or changing the production driver.

## Isolated reachability

With Docker `network none`, no host TCP connection can reach PostgreSQL. The
workable arrangement is to start the existing container without changing its
network isolation, configure TLS inside it, and run Deno inside the same
container against `127.0.0.1:5432`. The test process then uses TCP locally
inside the isolated container, while the database remains unpublished and
unreachable from the host or external services.

The exact required container changes are: start the existing stopped container,
install/configure local PostgreSQL TLS, make Deno and the C1 files available
inside it, and make the reviewed dependency cache/lockfile available inside it.
No port publication, network attachment, bind mount, or production SQL change is
required. `docker exec psql` may administer fixtures, but is not the actual
driver test.

## Proposed command

After the above prerequisites are confirmed, from the repository root, with
synthetic values supplied in the process environment (not `.env`):

```powershell
$env:C1_IT_DB_URL = 'postgres://c1_collector:synthetic@127.0.0.1:5432/postgres?sslmode=verify-full'
$env:C1_IT_COHORT = 'synthetic_c1_it_<unique-run>'
$env:C1_IT_REPLAY_WORK_ID = '<fixture-refresh-work-id>'
$env:C1_IT_STALE_RUN_ID = '<fixture-expired-run-id>'
$env:C1_IT_STALE_OWNER = 'synthetic-stale-owner'
$env:C1_IT_STALE_FENCE = '<fixture-stale-fence>'
$env:C1_IT_STALE_WORK_ID = '<fixture-expired-work-id>'
$env:NODE_EXTRA_CA_CERTS = '<path-inside-isolated-runtime>/synthetic-ca.pem'
deno test --cached-only --deny-import --no-lock --no-prompt `
  --deny-net --deny-env --deny-read=.env --deny-write --deny-run --deny-ffi `
  --allow-read=supabase/functions/c1-collect,tests/component_1/edge_collection `
  --allow-env=C1_IT_DB_URL,C1_IT_COHORT,C1_IT_REPLAY_WORK_ID,C1_IT_STALE_RUN_ID,C1_IT_STALE_OWNER,C1_IT_STALE_FENCE,C1_IT_STALE_WORK_ID,NODE_EXTRA_CA_CERTS `
  tests/component_1/edge_collection/postgres.integration.test.mjs
```

This command is executable only after all placeholder values are replaced by the
administrator fixture output and the runtime/cache/TLS prerequisites above are
confirmed. It must run inside the isolated container. Do not run it against
Supabase, YouTube, a published host port, or a real credential.

## Required coverage before execution is approved

The final fixture-driven suite must assert successful store commits and
rollback, identical replay without a second history row, conflicting replay
rejection, expired lease and stale-fence rejection, concurrent claim
serialization, attempt-budget reservation limits, collector
identity/permissions, and RLS visibility for both in-scope and synthetic
out-of-scope rows. Results must also record the exact runtime location and
container isolation metadata.
