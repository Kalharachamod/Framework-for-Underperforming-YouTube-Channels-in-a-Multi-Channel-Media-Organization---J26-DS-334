# Component 3 live results (nightly)

Live results keep the Audience Bridge Score up to date without any analyst computer being on. A GitHub
Actions job runs every night, collects new public YouTube data into Supabase, scores a rolling window and
publishes aggregate results that the dashboard's **Live Results** page (`/live`) reads.

Live results are **monitoring results**. The frozen thesis results remain the immutable Parquet research
snapshots (Derana-only research set); nothing here changes the methodology or replaces those results.

## Schedule and flow

`.github/workflows/component3-nightly.yml`, cron `30 18 * * *` (00:00 Sri Lanka time), plus a manual
**Run workflow** button (`collect` input: off = score the data already stored).

`python -m research.component_3.live` (`research/component_3/live.py`):

| Step | What happens |
|---|---|
| 1. Collect | For the channels in `config/research_channels.json`: channel details, the newest 50 uploads per channel (the busiest channel posts about 17 a day), and comments on videos published in the last 30 days (incremental: stops at threads already stored). |
| 2. Snapshot | A research snapshot (`source = supabase_postgresql_live`) of videos published in the last 90 days and their comments: **the same window for every channel**. |
| 3. Score | The frozen pipeline up to the Audience Bridge Score, with the same quick stages as the dashboard's organization analysis (topics, graph, features, metapath2vec, PPR, ABS, Louvain, explanations). |
| 4. Publish | Aggregates go to the `research.c3_live_*` tables. |

Options: `--no-collect`, `--window-days N` (default 90) and `--recheck-days N` (default 30).

## Storage (migration `0005_component3_live.sql`)

| Table | Content |
|---|---|
| `research.c3_live_runs` | One row per run (`live-YYYYMMDDTHHMMSSZ`): status `running`, `completed` or `failed`, window, snapshot and experiment IDs, counts, quota units and a safe error message. |
| `research.c3_live_bridge_scores` | Per run and ordered channel pair: score, components, confidence, shared commenter count, rank and status. |
| `research.c3_live_channels` | Per run and channel: videos, comments and unique commenters. |

RLS is enabled and `anon`/`authenticated` have no access; only the backend reads these tables.

The tables hold **aggregates only**: never commenter identifiers (raw or hashed) and never comment text. A
failed run rolls back, so it never leaves a partial result set; the dashboard keeps showing the last
completed run and warns about the failure.

## API (read-only)

`/api/v1/component-3/live` (`backend/api/component_3/live_routes.py`, `backend/services/component_3/live_results.py`):

- `GET /runs?limit=` lists the newest runs first, with `latest_completed_run_id`.
- `GET /bridges?run_id=&source=&limit=` returns the scores, channels and pairs-with-evidence count (default: latest completed run).
- `GET /history?source=&destination=&limit=` returns one pair's score over completed runs, oldest first.

The backend uses a read-only connection. A missing database or missing tables returns `503 storage_unavailable`,
and the page then shows the setup steps.

## Setup (once)

1. Create the tables: `python -m shared.database.migrate`.
2. In GitHub, open **Settings → Secrets and variables → Actions** and add `YOUTUBE_API_KEY`,
   `COMMENTER_HASH_SALT` (the team salt, so hashes match existing data) and `SUPABASE_DB_URL`.
3. Put `.github/workflows/component3-nightly.yml` on the default branch (`main`); GitHub only schedules
   workflows from there. The job checks out and runs the code of `component-3` (repository variable
   `C3_BRANCH` overrides it), so only this one file needs to be on `main`.
4. Push the workflow, then run **Actions → Component 3 nightly → Run workflow** once to check it.

## Notes and limits

- **Quota.** A night uses well under the 10,000-unit daily YouTube quota for the research set; `quota_units` is recorded per run. The quota resets at midnight Pacific time.
- **API key restrictions.** A key restricted to IP addresses will fail on GitHub's runners. Use an API-restricted key (YouTube Data API v3 only).
- **Runner minutes.** Public repositories run Actions free. Private repositories use the account's monthly free minutes; each run's duration is shown in the Actions tab.
- **Interpretation.** Scores are *potential* audience bridges. They are not evidence of audience migration, causality or growth.
- **Not yet built (optional).** A weekly full evaluation (HGT, node2vec and baselines) on the live snapshot.
