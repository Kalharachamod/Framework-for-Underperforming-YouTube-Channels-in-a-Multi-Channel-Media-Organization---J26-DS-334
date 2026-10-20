# Disposable PostgreSQL validation — 2026-10-18

Container: `c1-sql-test-f337cd70fa9d4922866dce767c607f66`.
Server: PostgreSQL 17.11. The container remains available.

Isolation was checked before execution: local Windows Docker named pipe,
network `none`, no published ports, no host/volume mounts, and tmpfs at
`/var/lib/postgresql/data`, `/var/run/postgresql`, and `/tmp`.
All database access used `docker exec` and `psql -X -v ON_ERROR_STOP=1`.
No environment files, external database URLs, Supabase credentials, real cohort
manifest or real source data were used.

Applied successfully, in documented order:
`002a_roles.sql`, `001_schema.sql`, `002b_access.sql`.
Production SQL was not modified. The read-only `003_verify_readonly.sql`
completed successfully as the actual `c1_collector` login.

Focused test source: `tests/component_1/test_c1_postgres_local.ps1`.
It requires these scripts already applied in the named isolated container;
its plain CREATE/INSERT fixtures intentionally fail on repeat execution.
It does not apply or repair production SQL. Synthetic cohort IDs are
`synthetic_c1_local_pending` and `synthetic_c1_local_enabled`, version `test`.
All approval references, channels, videos, runs, work and snapshots are synthetic.
Research/annotation fixtures exist only in this disposable database.

## Results

All focused assertions passed; no unexpected SQL errors occurred:

- Actual login verified: both session_user and current_user are c1_collector.
- Pending/disabled insert rejected; disabled metadata UPDATE affects zero rows.
- Enabled cohort channel/video/run/work/history inserts and allowed metadata,
  operational and coordination updates succeed.
- Off-allowlist channel insertion and video ownership changes rejected.
- Approval, admission, run schedule, task selection and migration tracking
  mutations rejected; migration tracking SELECT also denied.
- History UPDATE/DELETE, duplicate keys and overwrite UPSERT rejected for both
  history tables; final stored observations remain unchanged.
- NULL, reported zero and maximum bigint preserved. Negative counts rejected.
- Staged payload, observation timestamp and hash changes rejected by triggers.
- SET ROLE c1_owner rejected.
- INSERT/UPDATE/DELETE denied on synthetic research and annotation tables,
  including synthetic research.schema_migrations.

## Effective privileges and limitations

All nine C1 tables have RLS enabled. Collector table grants and column UPDATE
rights match the reviewed access script. There is no table-level UPDATE grant,
history mutation grant, migration-table access or role membership. All three C1
trigger functions are invoker functions and none is directly executable by the
collector. Trigger execution nevertheless succeeded on permitted writes.
Collector has C1 USAGE without CREATE, and no research/annotation schema USAGE.
The only installed extension is plpgsql; the audit found no foreign tables.

The local database has effective CONNECT and PUBLIC TEMP, but not database
CREATE. PUBLIC schema USAGE is also effective, without CREATE. Standard catalog
functions retain built-in executable paths. These are inherited/default platform
capabilities, not new grants from C1 SQL. TEMP exceeds a literal CONNECT-only
database allowlist and needs explicit assessment before deployment. No existing
PUBLIC privileges were changed to make the tests pass. This is not an unqualified
least-privilege approval or an exhaustive safety review of PostgreSQL built-ins.

The full read-only catalog report was captured in the host temporary directory:
`C:\Users\acer\AppData\Local\Temp\c1-local-audit-85baa94b3ae645e9a58a3b8539b6990b.txt`.
It contains local synthetic/catalog evidence, not external credentials or source
data. It is not a durable repository artifact.

These results do not establish live Supabase isolation, pooler authentication,
Edge environment isolation, runtime fencing, budgets, recovery, fairness,
exact replay validation or collection correctness. No collector runtime was
executed. No deployment, schedule, software installation or Git operation was
performed, and no other container was touched.
