# Quick Organization Analysis (dashboard: "Analyze Organization")

Code:
- [`research/component_3/analysis.py`](../../research/component_3/analysis.py): the runner
- [`backend/services/component_3/analysis_jobs.py`](../../backend/services/component_3/analysis_jobs.py): jobs
- [`backend/api/component_3/analysis_routes.py`](../../backend/api/component_3/analysis_routes.py): API
- [`frontend/src/features/component_3/pages/AnalyzePage.tsx`](../../frontend/src/features/component_3/pages/AnalyzePage.tsx): page

Tests:
- `tests/backend/test_component_3_analysis.py`
- `tests/component_3/test_analysis.py`
- `frontend/tests/analyze.test.tsx`

All tests use a fake API and fake runner. No real YouTube or Supabase calls are made.

## Purpose

The research dataset is the Derana channel set (`config/research_channels.json`). This feature lets a user analyse **any other YouTube media organization** from the dashboard, without command-line steps, in a few minutes.

## Flow

1. **Search** (`POST /analysis/discover`): the existing [organization discovery](org_discovery.md) finds the main channel and the sub-channels it links to, each with evidence and a confidence level. This costs about 100–150 quota units.
2. **Confirm:** the user ticks the channels that belong to the organization. High-confidence channels are pre-ticked. YouTube does not publish ownership, so this human confirmation stays part of the method. If no confirmed list exists yet, the choice is saved as `config/organizations/<slug>.json`. An existing list is never overwritten.
3. **Analyze** (`POST /analysis/jobs`) starts one background job, with live progress in the dashboard.

| Step | What | Uses |
|---|---|---|
| preflight | API key, salt, database URL, disk space, quota estimate | — |
| channels, videos, comments | Fresh collection into Supabase with **quick limits**: 15 newest videos per channel, 50 comment threads per video, no extra reply pages | existing collectors |
| snapshot | A research snapshot containing **exactly this run's records**, with source `supabase_postgresql_analysis` and `details.organization` | `export_research_snapshot(scope=…)` |
| research_data → explainability | Topic similarity, graph (with topic nodes), features, metapath2vec, Personalized PageRank, Audience Bridge Score, Louvain baseline, explanations | `pilot.run_pipeline` with `QUICK_STAGES` |
| icons | Public channel images for the dashboard (best effort, 1 unit) | `channel_icons` |

4. **Open results:** the dashboard switches to the new snapshot. The snapshot selector shows the organization, for example "Sirasa (quick) · rs-…".

## Why it is fast

| Kept | Skipped (run them later with the normal commands if needed) |
|---|---|
| Collection with small limits, topic similarity, graph, metapath2vec, PPR, Audience Bridge Score, Louvain, explanations | HGT (alternative model), node2vec (the slowest stage), the full evaluation (sparse and temporal re-runs) |

A typical job with about 10 channels needs a few minutes. Most of that time is comment collection (about one request per video).

## Separation from the research dataset

- Quick analyses never change `config/research_channels.json`, so the frozen thesis scope stays **Derana only**.
- Their snapshots contain only the analysed organization's records.
- The normal `--extract` snapshot (`run_collection --snapshot`) now exports **only the configured research channels**. Other organizations stored in the same Supabase database therefore never mix into the research snapshot.
- Quick-analysis snapshots are flagged `quick_analysis: true` in `/status`. Their results are **exploratory**: the samples are smaller than the research runs and no evaluation is run.

## Safety

- **Switch:** `API_ENABLE_ANALYSIS=false` disables search and jobs (`403`).
- **Limits:** one job at a time (`409`); 2–25 channels per job; a quota cap of 2,000 units per job (the estimated upper bound for 25 channels is far below it).
- **Records:** jobs are recorded in `data/raw/analysis_jobs/`. A job that was running when the API stopped becomes `interrupted`, never "completed".
- **Messages:** job messages and progress never contain secrets or commenter identifiers. Any `anon_…` value is redacted.
- **Interpretation:** results are potential audience bridges. They do not show audience migration, subscriber transfer, causality or growth.
