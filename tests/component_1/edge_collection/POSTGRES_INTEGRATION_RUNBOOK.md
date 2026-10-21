# C1 PostgreSQL integration test

Validated 2026-10-20: all 11 tests in `postgres.integration.test.mjs` passed (2
pending-phase, 9 enabled-phase) with the setup below. The test uses the real
`npm:postgres@3.4.7` driver through `postgresFactory`, the real `PostgresStore`,
`collect()` and HTTP handler, connected only as `c1_collector`. YouTube is
always mocked through the injected `fetcher`; the container has no network.

Run only against a disposable local container. Never against Supabase, the real
YouTube API, a published host port or a real credential. All passwords below are
throwaway values for the container.

## What the phases prove

- `pending` (bootstrapped cohort still pending/disabled): the real driver logs
  in as `c1_collector`; in-window `daily-start` and `continuation` through the
  handler return `503 GATE_CLOSED` with no YouTube call and no database change.
- `enabled` (after the operator approval SQL, inside the container only):
  concurrent claims on two connections give one lease and one `busy`; a failed
  transaction leaves no row; a staged channels response is committed once after
  a simulated crash and the stale lease is rejected (`LEASE_LOST`);
  continuations finish a mocked 41-channel run with one transient 503 retry (44
  attempts: 1 channels, 42 discovery, 1 candidates); 41 channel and 6 video
  snapshots are written once; repeated `daily-start`/`continuation` make no API
  call and no write; history UPDATE/DELETE/TRUNCATE are denied to the collector
  even with `c1.retention_purge` set; research, model views, channels,
  memberships, holdout flag and cohort approval are not writable/readable as
  required.

`integration/post_checks.sql` then checks, as the owner path, that every
`summary`, `outcomes` and `staged_response` is a jsonb `object`, the history
counts, and that the history trigger blocks the owner.

## Prerequisites (host)

- Docker; image `postgres:17` (17.11 validated).
- Linux Deno 2.9.7 binary (`deno-x86_64-unknown-linux-gnu.zip` from the Deno
  release; verify its published SHA-256 before use). Extract it into a new empty
  directory.
- The driver cache: on the host, with a fresh empty `DENO_DIR` and a scratch
  copy of the function lockfile (so the repository lockfile is not rewritten):

```powershell
$env:DENO_DIR = '<new empty dir>\deno_dir'
Copy-Item supabase/functions/c1-collect/deno.lock '<scratch>\deno.lock.copy'
deno cache --config supabase/functions/c1-collect/deno.json --lock='<scratch>\deno.lock.copy' supabase/functions/c1-collect/driver.mjs npm:postgres@3.4.7
```

Confirm the `postgres@3.4.7` integrity in the scratch lock equals the one in
`supabase/functions/c1-collect/deno.lock` (`--frozen` refuses only because the
committed lock has no `workspace` section).

## Container and Supabase-like setup

Scripts in `integration/` are LF-only (see its `.gitattributes`). Do not pipe
scripts into `docker exec` from PowerShell: it prefixes a byte-order mark that
breaks the first shell line. Copy files with `docker cp` instead.

```powershell
docker run -d --name c1-pgtest --network none -e POSTGRES_USER=sim_admin -e POSTGRES_PASSWORD=sim_admin_throwaway_local postgres:17
docker exec c1-pgtest mkdir -p /sql /checks /opt/c1/supabase/functions /opt/c1/tests/component_1/edge_collection
docker cp research/component_1/sql/. c1-pgtest:/sql/
docker cp tests/component_1/edge_collection/integration/. c1-pgtest:/checks/
docker cp supabase/functions/c1-collect c1-pgtest:/opt/c1/supabase/functions/
docker cp tests/component_1/edge_collection/postgres.integration.test.mjs c1-pgtest:/opt/c1/tests/component_1/edge_collection/
docker cp '<DENO_DIR>' c1-pgtest:/opt/c1/deno_dir
docker cp '<extracted>\deno' c1-pgtest:/usr/local/bin/deno
docker cp tests/component_1/edge_collection/integration/run_it.sh c1-pgtest:/opt/c1/run_it.sh
docker exec c1-pgtest sh -c 'chmod 0755 /usr/local/bin/deno && chown -R postgres:postgres /opt/c1'
docker exec c1-pgtest sh /checks/tls_setup.sh
```

`tls_setup.sh` creates a throwaway CA and a server certificate for
`DNS:localhost, IP:127.0.0.1`, enables `ssl`, and rewrites `pg_hba.conf` so
every TCP login, loopback included, is `hostssl ... scram-sha-256`. The image's
default `host all all 127.0.0.1/32 trust` would otherwise accept loopback TCP
without a password. Only the Unix socket stays `trust`, for `docker exec`
administration as `sim_admin`. Check that `sslmode=disable` and a wrong password
are both rejected before continuing.

Supabase-like roles, then the C1 SQL in Supabase order as the non-superuser
`postgres`, each over TLS with `ON_ERROR_STOP=1`:

```text
psql -U sim_admin (socket): CREATE ROLE postgres LOGIN NOSUPERUSER CREATEROLE CREATEDB PASSWORD '...';
                            GRANT CREATE ON DATABASE postgres TO postgres;
                            CREATE SCHEMA research; CREATE SCHEMA annotation;
psql "host=localhost user=postgres dbname=postgres sslmode=verify-full sslrootcert=/opt/c1/tls/ca.pem"
  -f 000_preflight_readonly.sql, 002a_roles.sql, 002a2_model_reader_role.sql,
     002a1_owner_membership.sql, 001_schema.sql, 002b_access.sql, 004_bootstrap_v0_3_0.sql
  ALTER ROLE c1_collector PASSWORD 'collector_throwaway_local';
  ALTER ROLE c1_model_reader PASSWORD 'reader_throwaway_local';
psql ... user=c1_collector ... -f 003_verify_readonly.sql
psql -U sim_admin (socket): CREATE TABLE research.c1_synthetic_probe (id integer);
```

The only expected diagnostic is
`002b_access.sql:98: WARNING: no privileges were
granted for "postgres"`
(database owned by `sim_admin`; PUBLIC CONNECT applies).

## Run

```powershell
docker exec -u postgres c1-pgtest sh /opt/c1/run_it.sh pending
docker exec -e PGPASSWORD=<postgres throwaway> c1-pgtest psql "host=localhost user=postgres dbname=postgres sslmode=verify-full sslrootcert=/opt/c1/tls/ca.pem" -v ON_ERROR_STOP=1 -f /checks/approve_enable.sql
docker exec -u postgres c1-pgtest sh /opt/c1/run_it.sh enabled
docker exec -e PGPASSWORD=<postgres throwaway> c1-pgtest psql "<same TLS conninfo>" -v ON_ERROR_STOP=1 -f /checks/post_checks.sql
docker rm -f -v c1-pgtest
```

`approve_enable.sql` is the operator approve/enable SQL from the deployment
checklist (as `postgres`, `SET LOCAL ROLE c1_owner`) with synthetic values; its
retention reference must equal the test's `C1_IT_RETENTION` default.

`run_it.sh` runs Deno as the unprivileged `postgres` OS user with:

- `--allow-net=localhost:5432` only (not `--deny-net`, which blocks the driver);
- `--cert /opt/c1/tls/ca.pem`, so `rejectUnauthorized: true` verifies the
  throwaway CA without weakening the production driver;
- `--allow-read=/opt/c1`, `--deny-write --deny-run --deny-ffi`,
  `--cached-only
  --deny-import --no-lock --no-prompt`;
- `--allow-env` for the test's `C1_IT_*` names plus the `PG*` names that
  `postgres@3.4.7` reads for options the driver does not set: `PGMAX_PIPELINE`,
  `PGBACKOFF`, `PGKEEP_ALIVE`, `PGFETCH_TYPES`, `PGPUBLICATIONS`,
  `PGTARGET_SESSION_ATTRS`, `PGTARGETSESSIONATTRS`, `PGAPPNAME`. With
  `--deny-env` the driver fails with
  `NotCapable: Requires env access to "PGMAX_PIPELINE"`.

Optional overrides: `C1_IT_COHORT`, `C1_IT_VERSION`, `C1_IT_MANIFEST_HASH`,
`C1_IT_RETENTION` (defaults: the v0.3.0 cohort, its deployed hash, and
`synthetic-integration-retention`). Without `C1_IT_DB_URL` every test skips.

## Not covered

Supabase pooler routing and its certificate chain, the Edge runtime and
packaging, lease expiry under real 75-second waits, memory/CPU limits, and the
real YouTube API. `tests/component_1/test_c1_postgres_local.ps1` is a separate,
older SQL-only script and remains not re-validated.
