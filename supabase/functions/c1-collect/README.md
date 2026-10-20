# C1 collector — local implementation, disabled

This code has not been served, deployed, or connected to Supabase or the real
YouTube API. Its store has run against a disposable local PostgreSQL 17 with the
real driver (see "Integration validation"). The real proposed cohort remains
pending and disabled. This implementation does not grant approval, provision
resources, read environment files, bootstrap inventory, configure authentication
at the gateway, schedule jobs or remove data.

Sources read before implementation:

- `docs/component_1_collection_design.md`
- `research/component_1/sql/README.md`, reviewed role/schema/access SQL and
  `LOCAL_VALIDATION_2026-10-18.md`
- `research/component_1/statistics_runner.py` and its synthetic test references

## Code boundaries

`index.ts` imports the Deno runtime wiring in `runtime.mjs`. `handler.mjs` owns
authentication, bounded POST parsing and sanitized HTTP results. `collector.mjs`
coordinates injected storage and transport dependencies. `youtube.mjs` uses only
fixed YouTube Data API endpoints, field projections, a 10-second timeout and a
128 KiB response cap. `core.mjs` contains validation, scheduling, canonical
hashes, budgets and numeric rules. `store.mjs` contains parameterized C1 SQL
transactions. `driver.mjs` lazily loads the pinned `postgres@3.4.7` dependency
from the function-local `deno.json`, with one TLS-verified connection and no
prepared statements. There are no shared writer imports or privileged credential
reads.

Bearer tokens are compared using SHA-256 fixed-length digests and the native
`node:crypto` timingSafeEqual primitive. Authentication completes before driver
loading, connections or API requests. Missing configuration fails closed. Errors
return fixed codes only; raw exceptions, responses, URLs and headers are not
logged. This function currently emits no logs.

## Configuration contract

No actual values or secrets are supplied here. A separately approved operator
would provide the following function-specific settings:

| Setting                             | Requirement                                                                                                                                                                                                                                                            |
| ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `C1_ACTIVATED`                      | Exact `true`; missing/other values disable collection                                                                                                                                                                                                                  |
| `C1_CRON_TOKEN`                     | High-entropy C1-only bearer token, 32–512 characters                                                                                                                                                                                                                   |
| `C1_COLLECTOR_DB_URL`               | Only database credential accepted; username exactly `c1_collector` or the pooler form `c1_collector.<20-char lowercase project ref>`, password, host and explicit `sslmode=require` or `verify-full`; no other URL options. Recommended: transaction pooler, port 6543 |
| `C1_YOUTUBE_API_KEY`                | Dedicated YouTube collection key                                                                                                                                                                                                                                       |
| `C1_COHORT_ID`, `C1_COHORT_VERSION` | Operator-controlled target, never request-supplied                                                                                                                                                                                                                     |
| `C1_MANIFEST_HASH`                  | Canonical approved manifest hash, matched exactly against cohort configuration                                                                                                                                                                                         |
| `C1_RETENTION_DECISION_REFERENCE`   | Nonempty approved decision reference, matched exactly against cohort configuration                                                                                                                                                                                     |

The driver verifies the server certificate even when the accepted URL says
`sslmode=require`. Do not weaken TLS to fix connectivity. Supabase pooler
routing and its certificate chain in the Edge runtime still require a first
deployed check. The pooler strips the project ref, so the server sees
`c1_collector`; both session and current user are checked in every store
transaction. The pinned `postgres@3.4.7` also reads a few `PG*` environment
variables for options the driver does not set (`PGMAX_PIPELINE`, `PGBACKOFF`,
`PGKEEP_ALIVE`, `PGFETCH_TYPES`, `PGPUBLICATIONS`, `PGTARGET_SESSION_ATTRS`,
`PGTARGETSESSIONATTRS`, `PGAPPNAME`); host, port, user, password, database and
TLS always come from the URL and `driver.mjs`.

Only `POST application/json` with exactly one property is accepted:
`{"action":"daily-start"}` or `{"action":"continuation"}`. Requests are limited
to 256 bytes and two seconds for body reading. Clients cannot supply collection
dates, SQL, cohort IDs, budgets or selected entity IDs. A processed HTTP
response does not itself establish successful collection; inspect the returned
run state and independent completion flags. Gateway `verify_jwt=false` is only
an eventual separately approved setting paired with this mandatory custom bearer
check; no gateway configuration was changed here.

## Durable execution

The database clock determines the Colombo 02:00–03:00 window, UTC scheduled
instant, deadlines and leases. Daily-start creates at most one run for that
instant. Continuation never creates a run. An unfinished run holds the
coordination slot; expired unfinished work is marked partial and reported before
another start. A live lease returns busy. Claims lock the operator-created
coordination row and increment its bigint fencing token, represented as a string
outside PostgreSQL. Each mutating transaction locks/checks that row and
validates the token, owner and expiry. Takeover workers may replay staged work,
but an old worker cannot stage or commit using its previous fence.

At run creation (2026-10-20 schema), the cohort's `c1.cohort_channels` rows must
match the approved `channel_ids`; a mismatch stops collection. The first run
sets the set-once `admission_published_after` (scheduled time minus
`admission_lookback_days`, 30). Only videos due today are frozen into
deterministic 50-ID refresh tasks: daily for days 0–30 after publication, weekly
until day 365 (age a multiple of 7, or last observation older than 7 days), then
never; SQL selects them and `refreshDue` re-checks each row. Due videos are
capped at 10,000 per run. The first requests refresh inventory, then batch
channel metadata/statistics. Discovery then creates one page task per channel,
using the persisted rotating start. Page N+1 is ordered after all channels' page
N tasks. A page whose uploads reach the admission cutoff completes that channel.
Waiting retries do not block other ready channels in the same phase. Missing
playlists, exhausted budgets, repeated tokens and page caps yield partial
coverage. Invalid page tokens record a failed page and restart newest-first
within remaining caps. After every discovery page has finished, new IDs are
batched 50 per task across channels; admission requires allowlist membership and
agreement with the channel whose immutable staged discovery page listed the ID,
and candidates published before the cutoff are recorded as skipped. Admissions
increment the coordination revision without altering original inventory
identities. History rows are keyed by entity and observation time; cohort/run
IDs are provenance. Videos also store `duration_seconds` and `category_id`;
channels store `country`, `default_language` and `topic_categories`.

Each HTTP dispatch, including retries, follows a committed reservation. Crashes
after reservation can consume an attempt even when no request was made.
Reservations protect the initial refresh attempts of later batches and the
candidate allowance; discovery also has its own inclusive attempt budget.
Transient transport/429/5xx failures allow at most two retries and persist a
next-attempt timestamp with exponential backoff/jitter. No worker sleeps to
retry. Authentication/quota failures terminate the run. Remaining tasks retain
their unattempted or unconfirmed state.

Each invocation permits at most six dispatches and twelve loop steps, with a
60-second soft deadline and no new work below a 15-second margin. Leases last 75
seconds. No database transaction spans an HTTP request. Transactions use local
UTC, a 5-second statement timeout, 1-second lock timeout and 10-second idle
transaction timeout. Plans are capped at 50 channels, 10,000 due videos, 1,000
work rows and 200 approved attempts per run; larger configurations fail closed.
The v0.3.0 cohort uses 200 total / 70 discovery / 20 candidate reserve. These
are implementation safety caps, not production budget approval.

Responses are staged with a canonical SHA-256 hash and actual UTC response
completion time. Replay hashes the staged body, uses its original observation
time, and atomically applies history/current metadata/work completion.
Per-entity canonical hashes guard existing snapshot keys: identical is a no-op,
conflicting is a validation failure. There is no history UPDATE or overwrite
UPSERT. Metadata updates exclude observations older than the current metadata.
Absent counts remain NULL; reported zero stays zero; nonnegative signed bigint
counts stay decimal strings. Unavailable IDs remain in inventory and receive
outcomes, without fabricated statistics. Invalid staged observations are
retained but marked failed; no cleanup is implemented.

`collection_work.outcomes` stores receipt/staging/commit times and bounded
per-ID outcomes (returned, invalid, unavailable, skipped, discovered, cutoff
reached). `collection_runs.summary` stores candidate completion, discovery and
candidate seeding flags, per-channel coverage and aggregate counts;
`inventory_complete` and `discovery_complete` retain their dedicated columns. No
new column grants or privileged routines are assumed. Cohort SELECT gates and
existing RLS are checked on transactions/statements; this is not a mechanism to
cancel an already issued HTTP request or retroactively revoke an already
committed transaction.

## Offline validation

From the repository root in PowerShell, with Node.js 24 already installed:

```powershell
$c1WorkspacePath = (Get-Location).Path
node --permission "--allow-fs-read=$c1WorkspacePath" --test --test-isolation=none ./tests/component_1/edge_collection/collection.test.mjs
```

Network, child processes and filesystem writes are not granted. Tests also block
global fetch, TCP/TLS and UDP entry points; all credentials are synthetic. The
test file imports only these local modules and Node built-ins. It never imports
the Deno runtime wiring or downloads/initializes the PostgreSQL driver. Read
permission covers the workspace to allow Node's Windows test-file resolution;
the tests do not read environment files or discover unrelated tests.

Result on 2026-10-20 after the schema revision, Node v24.19.0: see the latest
counts in the Deno section below. Original result on 2026-10-18: **41 tests
passed, 0 failed**. Tests cover authentication ordering, gates, driver
option/array binding, attempt reservations, fair page planning,
NULL/zero/bigint, ownership, replay, crash recovery, staged timestamps,
deadlines and stale fencing tokens. SQL store tests execute its methods against
a scripted query adapter. Concurrency/crash orchestration also uses an in-memory
model. The scripted adapter reproduces the real driver's jsonb parameter
encoding (a `$n::jsonb` string parameter would be stored as a JSON string), and
a source test requires every jsonb parameter to be cast `$n::text::jsonb`. These
mocks still do not prove PostgreSQL syntax, ACLs, locks or SQL races; the
integration run below covers the real driver.

## Integration validation (2026-10-20)

`tests/component_1/edge_collection/POSTGRES_INTEGRATION_RUNBOOK.md` was run in a
disposable PostgreSQL 17.11 container (`--network none`, no published port),
after the C1 SQL in Supabase order as a non-superuser `postgres`. Deno 2.9.7 ran
inside the container with the real `npm:postgres@3.4.7` (lockfile integrity
matched), as `c1_collector` over verified TLS with a required password, and
YouTube mocked through the injected fetcher. All 11 tests passed across both
phases: pending cohort returns `GATE_CLOSED` with no API call and no writes;
after in-container approval, concurrent claims yield one lease; rollback leaves
no row; a staged response is committed once after a simulated crash and the
stale lease is rejected; a mocked 41-channel run with one transient retry
completes with 41 channel and 6 video snapshots, each written once; repeat calls
write nothing; history UPDATE/DELETE/TRUNCATE are denied even with the purge
setting. `jsonb_typeof` of every summary, outcomes and staged response was
`object`. The first run found jsonb double-encoding, fixed with `::text::jsonb`.

## Remaining validation and deployment prerequisites

Serving, Edge packaging, Supabase pooler routing and the pooler certificate
chain in the Edge runtime remain unverified. No collector was served or executed
against real services. The pinned dependency still requires supply-chain review;
the function-local `deno.lock` pins its integrity. Lease expiry under real
connection races (75-second leases) was not exercised. Synthetic maximum-size
load tests must measure memory, the 2-second Edge CPU limit and total
transaction/handler time; per-statement timeouts alone do not bound the sum of a
multi-statement plan. The handler deadline is a scheduling bound, not a hard
cancellation of an in-flight transaction. Do not deploy based on mocked timing
results.

Operational integration remains unfinished: independent missed-run detection,
alert owner/escalation, Cron/HTTP request correlation and production capacity
monitoring are not provisioned. Summary counters/work outcomes are available for
that integration; no alert messages are sent. Retention is an admission gate,
not a deletion policy or automatic enforcement mechanism.

Before any deployment: obtain real cohort approval, agreed retention/capacity
and approved budgets/window; audit live effective/PUBLIC/inherited privileges
(including the local report's PUBLIC TEMP finding), custom-role routing and
environment-level privileged credential exposure; approve secrets/authentication
and deployment, validate C1-only canaries, establish independent monitoring,
then separately approve activation and scheduler jobs. Existing shared
privileges must not be changed as an implementation workaround. Token
rotation/revocation must coordinate the future scheduler and handler copies
without logging either.

## Deno validation (2026-10-18)

Validated with Deno 2.9.7, V8 15.0.245.2-rusty and TypeScript 6.0.3 on Windows.
Run only these scoped commands from the repository root:

```powershell
deno fmt --check supabase/functions/c1-collect tests/component_1/edge_collection
deno lint --config supabase/functions/c1-collect/deno.json supabase/functions/c1-collect tests/component_1/edge_collection
deno check --cached-only --deny-import --no-lock --config supabase/functions/c1-collect/deno.json supabase/functions/c1-collect/index.ts tests/component_1/edge_collection/collection.test.mjs
deno test --cached-only --deny-import --no-lock --config supabase/functions/c1-collect/deno.json --no-prompt --deny-read=.env --deny-net --deny-env --deny-write --deny-run --deny-ffi --allow-read=supabase/functions/c1-collect tests/component_1/edge_collection/collection.test.mjs
```

Tests use synthetic credentials and injected transports/query adapters only. The
source guard needs read access only to the C1 function directory. No permission
is granted to read environment files. A Deno-specific test checks denied
network, environment, write, subprocess, FFI and `.env` read permissions without
reading secrets or opening connections. `--deny-net` controls runtime
connections; `--cached-only` and `--deny-import` also constrain module
resolution. Stop and report missing dependencies before any separately
authorized fetch. The runtime pins `npm:postgres@3.4.7`; it is lazily imported,
never initialized by these tests.

Removed Deno's unsupported `allowJs` option. `checkJs: false` remains explicit:
`deno check` checks the TypeScript entry/graph but does not establish static
type safety of the JavaScript implementation or mocked adapters. The local lint
config excludes only `require-await`: async API wrappers and promise-returning
test doubles intentionally preserve promise/rejection semantics even without a
local await. Other recommended rules remain enabled, including unused-variable
detection. Formatting is Deno's default; unused callback bindings were
removed/underscored.

Local checks do not establish Supabase deployment compatibility, real PostgreSQL
driver behavior, SQL correctness, transaction/lease race behavior, ACL/RLS
isolation, Edge runtime packaging, certificate/pooler routing, resource limits
or operational readiness. No serving, database integration tests, SQL,
deployment or scheduling is included in this validation. Activation and all
approval gates remain unchanged.

Final local results on 2026-10-18:

- `deno fmt --check`: passed, 11 files checked.
- `deno lint` with the documented local rule configuration: passed, 9 files
  checked.
- `deno check`: passed for the entry and test graph, with `checkJs: false` as
  noted.
- Permission-restricted `deno test`: 42 passed, 0 failed (153 ms).

The first formatting pass found 10 unformatted files; the first lint pass found
39 `require-await` diagnostics and two unused callback bindings. The unsupported
`allowJs` setting was removed. The first added permission assertion failed
because out-of-scope reads had `prompt` state; explicit `.env` read denial and
`--no-prompt` corrected the test command without reading any file. All 41
pre-existing mocked tests passed before and after these changes. No lockfile was
generated; dependency lock/supply-chain review remains outstanding.

Results on 2026-10-20 after the pooler-username and jsonb fixes (same commands):

- `deno fmt --check`: passed, 13 files checked.
- `deno lint`: passed, 10 files checked.
- `deno check`: passed for the entry and test graph.
- Permission-restricted `deno test`: 54 passed, 0 failed.
- Node v24.19.0 `node --test`: 53 passed, 0 failed. Added: pooler username
  accept/reject cases, fake-adapter jsonb encoding, and the `::text::jsonb`
  source check. With the old `$n::jsonb` casts, 14 tests fail.

Earlier results on 2026-10-20 after the entity-keyed schema revision:

- `deno fmt --check`: passed, 13 files checked.
- `deno lint`: passed, 10 files checked.
- `deno check`: passed for the entry and test graph.
- Permission-restricted `deno test`: 51 passed, 0 failed.
- Node v24.19.0 `node --test`: 50 passed, 0 failed (the Deno-only sandbox test
  is skipped under Node). 43 pre-existing tests were updated for the new SQL and
  six-dispatch limit; 7 tests were added (admission cutoff and due selection,
  refresh policy, duration/category/country/language/topics parsing, discovery
  cutoff and skipped candidates, 41-channel gate, cutoff-completed channel,
  cross-channel candidate seeding).
