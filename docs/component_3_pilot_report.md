# Component 3 Controlled Real-Data Pilot (STEP 26)

Run: 2026-10-18T21:11:12+00:00 to 2026-10-18T21:11:18+00:00 (UTC) · Snapshot: `not created`

> Pilot results validate the pipeline on a small real sample. They do not show audience migration, causal influence, subscriber transfer or future growth, and three channels are too few for general conclusions.

## Configuration

| Setting | Value |
|---|---|
| Channels | 3: TV Derana (owned), Dream Star (owned), Derana City Of Music (owned) |
| Channel note | eTunes is not in the approved Derana channel set; Derana City Of Music is the music-profile substitute. |
| Videos per channel (max) | 15 |
| Comment threads per video (max) | 50 (all replies fetched: False) |
| Observation window | newest videos, no date limit |
| Retries / timeout | 3 retries, 30.0 s |
| Quota cap | 500 units |
| Topic clusters / seed | 10 / 42 |
| Sparse simulations | fractions (0.5,), seeds (0, 1) |

## Preflight

| Check | Status | Detail |
|---|---|---|
| environment variables | fail | YOUTUBE_API_KEY: MISSING, COMMENTER_HASH_SALT: MISSING, SUPABASE_DB_URL: set |
| YouTube Data API v3 client | fail | MissingAPIKeyError |
| channel ids | pass | 3 selected from configuration ({'owned': 18}) |
| shared database (read-only) | pass | reachable; 3 of 3 selected channels already stored |
| output directories | pass | data directory writable |
| disk space | pass | 13.2 GB free (minimum 1.0 GB) |
| pipeline dependencies | fail | missing: ['networkx', 'gensim', 'torch', 'torch_geometric', 'sentence_transformers'] |
| commenter pseudonymization | fail | PrivacyConfigError |
| existing snapshots intact | pass | 1 research snapshot(s) verified |
| new snapshot, no overwrite | pass | a new rs-<timestamp> id is created; existing ids are refused by create_research_snapshot |
| quota estimate | pass | upper bound 53 units (cap 500) |

Quota estimate (upper bound): 53 units {'channels.list': 2, 'playlistItems.list': 3, 'videos.list': 3, 'commentThreads.list': 45, 'comments.list': 0}.

## Collection

Not executed.

## Channel registry

| Measure | Value |
|---|---|
| Configured channels | 18 {'owned': 18} |
| Selected for this run | 3 (groups ['owned']) |
| Research plan | — |
| Gaps | none |
| Duplicate / invalid ids | none / none |

## Pipeline stages

| Stage | Status | Time (s) | Artifact | Details |
|---|---|---|---|---|

## Research validity checks

| Check | Status | Detail |
|---|---|---|

## Errors, warnings and limitations


**Recommendation:** remediate: a required preflight check failed, nothing was collected
