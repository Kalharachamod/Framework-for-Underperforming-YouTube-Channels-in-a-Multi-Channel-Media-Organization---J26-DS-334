# Component 1

**Channel-Specific Growth Opportunity Prediction with Pooled Learning**
Owner: Samarasinghe S I (IT23333802)

## Planned modules
- Normalised indicators (views/subscriber, views/day, likes and comments per 1,000 views)
- Channel-relative growth labels (above-baseline, top-quartile)
- Similarity-weighted pooled learning across niche-similar channels
- Baselines: Random Forest, XGBoost, LightGBM
- SHAP / feature importance and confidence levels
- Time-based train-test validation

## Folders
`preprocessing/` · `model/` · `evaluation/` · `notebooks/` · `results/` (git-ignored)


## Read-only data audit

From the repository root, run `python research/component_1/audit_data.py` after
configuring `COMPONENT1_DB_URL` locally with the `component1_readonly` role.
The script discovers live columns and primary keys before building aggregate
queries. It explicitly begins a read-only repeatable-read transaction, verifies
the role and transaction state, uses UTC and 30-second statement / 5-second lock
timeouts, and rolls back after reading. Connection startup options alone are not
sufficient with every connection pooler.

Timestamped JSON reports are written only after a complete audit to `results/`,
which is ignored by Git. They include column types, row/distinct counts, missing
identifiers/dates/numeric metrics, intended-grain duplicates, date ranges,
per-entity snapshot/day coverage and gaps, and daily frequencies. Video-history
channel counts are derived through the current video mapping. No source rows,
titles, connection URLs, or raw driver errors are exported. Read-only role/RLS
visibility defines the audit scope; gap thresholds describe observations rather
than an assumed schedule. A missing schema/grain column stops the audit.

Run offline safety checks with
`python -m unittest discover -s tests/component_1 -p test_audit_data.py -v`.
Do not commit generated reports or `.env`. Reports are diagnostic and do not
establish training readiness without a forecast horizon and leakage-safe splits.


## Manual statistics runner (unscheduled; database writes disabled)

The CLI separates synthetic fixtures, offline preflight, replay, and explicit
`--live` manual dry runs. It does not approve or enable the proposed cohort.
Manual dry-run authorization is separate from cohort approval and any future
scheduled collection. No scheduler or database writer is connected to this runner.
Shared imports may load local environment settings; the runner never prints them.

Offline commands from the repository root (no API or database connections):

```powershell
.venv/Scripts/python.exe -m research.component_1.statistics_runner --offline-preflight --dry-run --api-budget 100
.venv/Scripts/python.exe -m research.component_1.statistics_runner --manifest tests/component_1/fixtures/c1_cohort.json --fixture tests/component_1/fixtures/c1_statistics.json --dry-run
.venv/Scripts/python.exe -m unittest discover -s tests/component_1 -p "test_*.py" -v
.venv/Scripts/python.exe -m pytest tests/shared/test_youtube_client.py -q
.venv/Scripts/python.exe -m compileall -q research/component_1/statistics_runner.py tests/component_1
git diff --check
```

The shared-client test command requires pytest (declared in requirements.txt). The Component 1 unittest suite includes mocked
coverage of the shared client retry and failure behavior.

Replay an existing batch or successful raw response without fetching, changing its
original observation timestamp/payload, or writing to a database. Replace the path:

```powershell
.venv/Scripts/python.exe -m research.component_1.statistics_runner --manifest tests/component_1/fixtures/c1_cohort.json --replay "PATH_TO_SAVED_SYNTHETIC_BATCH" --dry-run
```

For live replay use the matching live manifest instead. Checksums detect accidental
corruption; they do not establish authenticity. Replay performs validation only.

Future connected commands below are examples, **not authorization to execute now**.
First obtain separate manual-run authorization; persistent live fetching also
requires an agreed retention policy.
Set `COMPONENT1_DB_URL` and `YOUTUBE_API_KEY` locally without putting secrets in
command history. The database URL must authenticate as `component1_readonly`.
Replace `AGREED_DAYS` with a positive integer from that policy and
`LOCAL_POLICY_REFERENCE` with its reference; neither is an assumed approved value.
The example budget of 100 attempts, 10 pages/channel and 2 retries/request must be
chosen for the actual run. Discovery may remain incomplete within these limits.

Read-only **real database connection**, no YouTube requests:

```powershell
.venv/Scripts/python.exe -m research.component_1.statistics_runner --live --preflight-only --dry-run --api-budget 100 --max-pages 10 --max-retries 2
```

Manual live dry run: **real database and YouTube connections**, local outputs only:

```powershell
.venv/Scripts/python.exe -m research.component_1.statistics_runner --live --dry-run --api-budget 100 --max-pages 10 --max-retries 2 --payload-retention-days AGREED_DAYS --retention-policy-ref "LOCAL_POLICY_REFERENCE"
```

Memory-only manual live dry run: **real database and YouTube connections**;
not executed as part of implementation. It requires separate manual authorization
and locally configured `COMPONENT1_DB_URL` / `YOUTUBE_API_KEY`:

```powershell
.venv/Scripts/python.exe -m research.component_1.statistics_runner --live --dry-run --no-persist --api-budget 100 --discovery-budget 20 --max-pages 10 --max-retries 2
```

`--no-persist` keeps fetched payloads and temporary inventory in memory. It does
not read saved inventory, create directories/locks, save payloads, batches,
inventory or reports, or delete existing files. Its inventory starts from the
verified read-only database bootstrap. It has no replay artifacts and no durable
admissions; later runs must bootstrap again. The console summary contains counts
only: channel/video IDs requested (once per logical request, retries excluded),
unique matching IDs returned per batch (including invalid records), unavailable
IDs omitted from successful responses, validation failures, and unconfirmed IDs
from failed requests. Unattempted batches after a global stop are not counted as
requested or unavailable. API attempt counts include every retry/page. Any
failure or incomplete discovery exits nonzero. Database writes and scheduling
remain disabled. Do not redirect console output into a file if no persistence is
required. The runner does not control external terminal/session logging.

Only modes that persist live API payloads require retention settings. Read-only
preflight neither persists inventory/API payloads nor deletes files and needs no
retention settings. An offline
preflight cannot know selected video counts without the database; connected
preflight verifies the effective role and read-only repeatable-read transaction
before a parameterized cohort-only video inventory query. It uses connect,
statement, lock and idle transaction timeouts and always rolls back/closes.
There is no fallback to shared privileged URLs and no commit/write helper.
Visibility is limited by the read-only role and RLS; no full-database visibility
is asserted. Existing stable inventory is merged with the bootstrap inventory.

Every attempted HTTP request counts against the live attempt budget, including
pagination, retries and network failures. Supported endpoints cost one quota unit
per attempt; this conservative counter differs from the shared client's answered
quota estimate. Invalid credentials, unauthorized responses, quota exhaustion and
budget exhaustion stop further transport calls. Transient errors alone receive
bounded backoff; retries are limited to 0..5 and pages to 1..200 per channel.
Any failed/incomplete collection exits nonzero, including pagination limits,
missing items and validation failures. Estimates are minimum planning figures,
not guarantees of complete discovery or refresh.

Inventory revisions retain old/unavailable IDs; metadata must validate channel
membership before new admission. Missing metrics remain NULL. Validated records
and successful raw live responses are immutable local files with original UTC
observation timestamps and checksums. A failed run can leave partial replayable
artifacts; these never imply complete collection. Interrupted locks or incomplete
JSON require manual inspection while no run is active; nothing is auto-deleted.

CLI state is Git-ignored under
`research/component_1/results/statistics_runner/fixture/<manifest-hash>/` and
`research/component_1/results/statistics_runner/live/<manifest-hash>/`.
Mode markers reject mixing synthetic and live state. Legacy unclassified inventory
cannot become live inventory implicitly. Each run writes its report and batches
under `run_<id>/`; successful raw responses use `payload_*.json`. Inventory revisions
are stored at the cohort root. Manifest changes require explicit migration.

Retention remains an operator prerequisite: `--payload-retention-days` and
`--retention-policy-ref` record an agreed setting, not proof of policy approval.
No approved duration, automatic cleanup, or compliance guarantee is supplied.
Operators must arrange review/removal of payloads, derived batches, inventory and
reports under their agreed policy; no existing files are automatically deleted.
Stable ID preservation across runs does not authorize indefinite data retention.
Credentials and all generated live artifacts must remain outside Git. Only
invented synthetic fixtures belong under tests.


### Inventory refresh and discovery budgets

Requests run in this order: existing inventory videos (batches of 50), channels,
upload discovery, then metadata for newly discovered candidates. Existing IDs
are not fetched twice. Inventory refresh reserves one initial attempt per batch
before any API request. If the budget cannot cover these initial attempts the
run fails before fetching. Retry attempts cannot consume the one-attempt reserve
for later inventory batches. This protects refresh from discovery starvation;
it cannot guarantee success when credentials, quota, network or metadata fail.

For 1,186 existing videos the reserve is 24 attempts, inside the overall
`--api-budget 100`. `--discovery-budget 20` is a separate global cap for
playlistItems attempts across all channels, including retries. `--max-pages 10`
is still a per-channel page cap. Neither cap adds to or overrides the overall
100-attempt limit. A discovery cap of zero skips discovery requests and marks
channels incomplete. Discovery is round-robin: each eligible channel gets one logical page before
any channel gets its next page. Exhausted/failed/page-limited channels leave the
rotation. Retries belong to the current page and consume the same global budget;
a retry-heavy run or a budget smaller than the eligible channel count can still
stop before every channel gets a successful first page. Completion and returned
page counts are reported per channel; no complete-discovery claim is inferred
from reaching the budget.

Summaries report endpoint `attempts`, `initial_attempts`, `retry_attempts` and
`successful_requests`. Attempts equal initial plus retry attempts; successful
requests are completed API list responses, not counts of validated records.
They also report inventory refresh completion independently from discovery,
with reasons for incomplete channels. Incomplete discovery produces a nonzero
exit status even when all existing inventory videos were refreshed successfully.
New candidate admission still requires schema validation, manifest membership
and agreement with the channel whose uploads playlist supplied the candidate.
The memory-only mode retains no artifacts and requires no retention settings.


### Inventory results versus candidate results

`inventory_refresh` describes only IDs present at the start of the run;
`new_candidates` describes only newly discovered IDs outside that original set.
Both groups report selected/requested/returned video counts, `unavailable` IDs
omitted from successful responses, `invalid` returned records, `failed_requests`
(logical requests that attempted transport but never returned successfully),
`successful_requests`, `unattempted_requests`, and `unconfirmed` IDs in failed
requests. Retries are counted separately by endpoint, not as extra failed logical
requests. Returned counts include invalid records.

`all_requests_completed` means every planned batch returned a successful API
response. `all_videos_returned` means every selected ID appeared in a response.
`complete` remains strict: both conditions must hold and invalid must be zero.
Thus a successful batch omitting an inventory ID has zero request failures yet
is incomplete. Omission is an unavailable observation, never confirmation of
deletion; original IDs remain in inventory. Candidate failures cannot change the
inventory group's flags. Overall collection stays incomplete/nonzero for missing
videos, invalid records, failed requests or incomplete discovery.
