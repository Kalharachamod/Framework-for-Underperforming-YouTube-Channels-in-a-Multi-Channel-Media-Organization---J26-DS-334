# Component 3: System Architecture

**Diffusion-Based Cross-Channel Audience Bridge Scoring** ("Growth Intelligence")

This document describes the architecture as it exists in the repository. Paths are relative to the repository root. The methodology and the equations are in [component3_final_methodology.md](component3_final_methodology.md), and a guided walk-through is in [component3_system_guide.md](component3_system_guide.md).

---

## 1. Overview

The system has five layers: **data, storage, research pipeline, service and presentation**. It also has three ways to run the pipeline.

```
                         ┌───────────────────────────── ENTRY POINTS ─────────────────────────────┐
                         │  A. Command line (thesis runs)   B. Analyze Organization   C. Nightly job │
                         │     run_collection + pilot           (dashboard)           (GitHub Actions)│
                         └───────────────┬───────────────────────────┬───────────────────────┬──────┘
                                         ▼                           ▼                       ▼
┌──────────────────── 1. DATA LAYER ─────────────────────────────────────────────────────────────────┐
│ YouTube Data API v3 ──► Shared collectors (shared/data_collection/)                                 │
│                         channels · videos · comments · org discovery · quota · retries              │
│                         commenter ID → "anon_" + HMAC-SHA256(salt, id)  before storage              │
└─────────────────────────────────────────────┬───────────────────────────────────────────────────────┘
                                              ▼
┌──────────────────── 2. STORAGE LAYER ──────────────────────────────────────────────────────────────┐
│ Supabase PostgreSQL (schema research)      shared team store of collected rows + live result tables  │
│         │ export                                                                                     │
│         ▼                                                                                            │
│ Research snapshots  data/snapshots/research/rs-<time>/   Parquet + SHA-256 manifest, never modified  │
│ Results             data/processed/component_3/<snapshot>/<stage>/<experiment-id>/   write-once     │
└─────────────────────────────────────────────┬───────────────────────────────────────────────────────┘
                                              ▼
┌──────────────────── 3. RESEARCH PIPELINE (research/component_3/, run_pipeline in pilot.py) ────────┐
│ research_data ─► topics (E5) ─► graph ─► features ─┬─► metapath2vec ─┐                              │
│ (DuckDB checks)                                    ├─► HGT (alt.)    ├─► Audience Bridge Score ─► explainability
│                                                    └─► PPR ──────────┘          │                    │
│                                         baselines: Louvain · node2vec · shared commenters            │
│                                         evaluation: agreement · top-k · temporal · sparse · runtime  │
└─────────────────────────────────────────────┬───────────────────────────────────────────────────────┘
                                              ▼
┌──────────────────── 4. SERVICE LAYER (backend/, FastAPI) ──────────────────────────────────────────┐
│ /api/v1/component-3/*            read-only: stored Parquet results, read with DuckDB                │
│ /api/v1/component-3/analysis/*   organization search and analysis jobs (one at a time)              │
│ /api/v1/component-3/live/*       nightly live results from Supabase (read-only, offline copy)      │
└─────────────────────────────────────────────┬───────────────────────────────────────────────────────┘
                                              ▼
┌──────────────────── 5. PRESENTATION LAYER (frontend/, React 19 + Vite + TypeScript) ───────────────┐
│ Welcome  /  ─►  Analyze Organization  ─►  Dashboard pages (Overview, Bridges, Explainability, …)   │
└─────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Data layer

| Part | Path | Responsibility |
|---|---|---|
| YouTube API client | `shared/data_collection/youtube_api_client.py` | Calls `channels.list`, `playlistItems.list`, `videos.list`, `commentThreads.list`, `comments.list`, `search.list` and `channelSections.list`. It counts quota units, retries transient errors, and maps errors to typed exceptions. The API key is read from `.env` only. |
| Collectors | `channel_collector.py`, `video_collector.py`, `youtube_comment_collector.py` | Turn API resources into validated records. Comments can be collected incrementally (stopping at threads already stored). |
| Organization discovery | `org_discovery.py` | Finds an organization's main channel and the channels it links to, then ranks them by evidence. A linked channel that YouTube no longer has is skipped. |
| Collection runner | `run_collection.py` | The command-line run for the research channels (`config/research_channels.json`), with an optional snapshot export. |
| Privacy | `shared/utils/privacy.py` | `anon_` + HMAC-SHA256 pseudonyms, applied before storage. It fails closed without the salt. |

---

## 3. Storage layer

| Store | Technology | Contents | Why |
|---|---|---|---|
| **Supabase** | PostgreSQL, `psycopg`, migrations in `shared/database/migrations/` (0001–0005) | `research.channels`, `videos`, `comments`; live tables `c3_live_runs`, `c3_live_bridge_scores`, `c3_live_channels` | One online store the whole team shares. Row-level security is on and anonymous access is revoked. |
| **Research snapshots** | Parquet (`pyarrow`) + manifest with SHA-256 checksums | Frozen copies of channels, videos and comments | Reproducibility: every analysis reads exactly one snapshot. |
| **Results** | Parquet + JSON manifests | One folder per stage and experiment ID (for example `bridge/abs-7cf3eab938ad/`) | Write-once. An ID is a hash of the inputs and settings, so identical runs are reused. |
| **Local caches** | JSON | Channel icons; the offline copy of live results (`data/cache/component_3_live/`) | Fast pages, and a working dashboard when the database is unreachable. |

---

## 4. Research pipeline

`run_pipeline(snapshot_id, config)` in `research/component_3/pilot.py` runs the stages in order. It stops at the first failure.

| Stage | Module | Output folder | Gives the score |
|---|---|---|---|
| research_data | `preprocessing/research_dataset.py` (DuckDB) | datasets in the snapshot folder | validated inputs |
| topics | `model/topic_similarity.py` (multilingual-e5-small + KMeans) | `topics/top-…/` | **T** (topic similarity), coverage |
| graph | `preprocessing/hetero_graph.py` | `graph/` | the heterogeneous graph |
| features | `preprocessing/graph_features.py` | `features/asof-…/` | **n** (shared commenters) |
| metapath2vec | `model/metapath2vec.py` (gensim skip-gram) | `embeddings/m2v-…/` | **E** (embedding cosine) |
| HGT (alternative) | `model/hgt.py` (PyTorch Geometric) | `embeddings/hgt-…/` | an optional replacement for E |
| ppr_diffusion | `model/ppr_diffusion.py` (SciPy sparse) | `diffusion/ppr-…/` | **D** (diffusion) |
| audience_bridge | `model/audience_bridge.py` | `bridge/abs-…/` | **score** = (⅓D + ⅓E + ⅓T) × n/(n+3) × coverage |
| louvain / node2vec | `model/baselines.py` | `baselines/` | baselines |
| explainability | `explainability/` | `explanations/xpl-…/` | decomposition, reasons, evidence |
| evaluation | `evaluation/` | `evaluation/eval-…/` | agreement, top-k, temporal, sparse, runtime |

**How the results move between stages:**
- Each stage passes its result to later stages **in memory** (the `st` dictionary) and also **saves it to disk**.
- The score stage receives D, E, T and n. It first checks that all of them come from the **same snapshot and graph**, then joins them into one table with one row per directed pair.
- It applies the equation and **rebuilds every score** as a check before saving.

**Pipeline profiles:**

| Profile | Stages | Used by |
|---|---|---|
| Full | all stages, including HGT, node2vec and evaluation | thesis runs (command line) |
| Quick | research_data, topics, graph, features, metapath2vec, PPR, score, Louvain, explanations | Analyze Organization, nightly live job |
| Complete | adds HGT, node2vec and evaluation to a quick snapshot | the "Complete analysis" button |

---

## 5. Entry points (the three flows)

### A. Thesis research (command line)
`run_collection --snapshot` → snapshot of the 18 Derana research channels → full pipeline → stored results.

### B. Analyze Organization (dashboard)
1. The **Welcome** page links to **Analyze an organization**.
2. **Search:** `POST /analysis/discover`, which runs organization discovery.
3. **Confirm channels:** the user ticks the channels that belong to the organization.
4. **Analyze:** `POST /analysis/jobs` starts one background job. It does quick collection (15 videos per channel, 50 comment threads per video) → a snapshot of exactly that run → the quick pipeline. Live progress is shown per channel.
5. **Open results:** the dashboard switches to the new snapshot.
- **Limits:** one job at a time; 2–25 channels; a quota cap.

### C. Nightly live results (GitHub Actions)
- `.github/workflows/component3-nightly.yml` runs at 00:00 Sri Lanka time on GitHub's servers, so no computer needs to be on.
- `python -m research.component_3.live` collects new data → takes a **rolling 90-day window, the same period for every channel** → runs the quick pipeline → publishes aggregates to the `research.c3_live_*` tables.
- A failed run, including a run where collection fails for every channel, is recorded as failed and publishes nothing.

---

## 6. Service layer (backend)

`backend/main.py` creates the FastAPI app. Errors map to clear codes: 404, 422, 409 (busy), 403 (analysis disabled), 502 (YouTube error), 503 (storage unavailable) and 504 (timeout).

| Router | Prefix | Main endpoints | Reads from |
|---|---|---|---|
| `routes.py` | `/api/v1/component-3` | `/status`, `/dashboard/*`, `/bridge/pairs`, `/bridge/{source}/destinations/{destination}`, `/channels/*`, `/graph/summary`, `/topics/similarity`, `/models/neural`, `/evaluation/*`, `/experiments/runs` | stored Parquet results (DuckDB), read-only |
| `analysis_routes.py` | `…/analysis` | `GET /config`, `POST /discover`, `POST /jobs`, `GET /jobs/{id}`, `POST /complete` | YouTube API, Supabase, the pipeline |
| `live_routes.py` | `…/live` | `/runs`, `/bridges`, `/history` | Supabase live tables (read-only connection, offline copy) |

**Services:**

| Module | Role |
|---|---|
| `service.py`, `dashboard.py`, `research_views.py` | read stored results |
| `analysis_jobs.py` | background jobs and progress |
| `live_results.py` | live results: fast failure on a blocked network, plus the offline copy |

**Privacy:** no endpoint returns commenter identifiers or comment text, only aggregates.

---

## 7. Presentation layer (frontend)

React 19 + Vite + TypeScript, in `frontend/src/`. The router is in `routes/AppRoutes.tsx`.

| Route | Page | Shows |
|---|---|---|
| `/` | Welcome | the logo and the start button (opens Analyze Organization) |
| `/dashboard` | Overview | KPI cards, top channels by potential bridges, live trend, bridge network, strongest bridge, pipeline |
| `/bridges` | Audience Bridges | inbound and outbound bridges per source, full ranking |
| `/explainability` | Explainability | how a score is built, reasons, evidence (opens on the strongest bridge) |
| `/channels` | Channel Explorer | one channel's audience, coverage, bridges and content neighbours |
| `/pipeline` | Pipeline Graph | the stored pipeline runs and settings |
| `/graph` | Graph Intelligence | node and relation types and the models built on the graph |
| `/topics` | Topic Intelligence | channel → topic flow, similarity wheel and matrix |
| `/neural` | Neural Models | metapath2vec and HGT, training curves |
| `/evaluation` | Baselines & Evaluation | agreement with the baselines and components |
| `/experiments` | Experiments | every stored run and snapshot |
| `/live` | Live Results | nightly runs, current top bridges, trends |
| `/analyze` | Analyze Organization | search → confirm → analyze → compare |
| `/status` | System Status | API and data health |

- **Selectors:** the top bar has the **Snapshot** and **Scoring experiment** selectors. Every page shows the selected snapshot's stored results.
- **Thesis results:** select `rs-20261010T081534Z`.

---

## 8. Deployment and runtime

| Where | What runs |
|---|---|
| Analyst computer | FastAPI backend (`uvicorn backend.main:app --port 8000`), the React dev server (`npx vite`, port 5173), command-line research runs |
| Supabase (cloud) | PostgreSQL: collected data and live results |
| GitHub Actions (cloud) | the nightly live pipeline; secrets `YOUTUBE_API_KEY`, `COMMENTER_HASH_SALT`, `SUPABASE_DB_URL` |
| YouTube (Google Cloud) | Data API v3: 10,000 quota units per day |

---

## 9. Cross-cutting properties

| Property | How it is achieved |
|---|---|
| **Reproducibility** | immutable checksummed snapshots; content-addressed experiment IDs; fixed seeds; pinned E5 revision; `requirements-lock.txt` |
| **Correctness** | input consistency checks (same snapshot and graph); every score rebuilt from its parts (error 0); unit and integration tests (pytest, vitest) |
| **Privacy** | HMAC pseudonyms before storage; aggregates only in the API and the live tables; secrets only in `.env` and GitHub Secrets |
| **Robustness** | stop at the first failed stage; write-once results; quota accounting; dead linked channels skipped; offline copy of live results |
| **Separation** | thesis results (Derana, frozen snapshots) are kept apart from quick analyses and live monitoring results |

---

## 10. Technology stack

| Area | Tools |
|---|---|
| Language | Python 3.13, TypeScript |
| Data | YouTube Data API v3, Supabase PostgreSQL, Parquet (`pyarrow`), DuckDB, pandas |
| Graph and models | NetworkX, SciPy (PPR), gensim (metapath2vec, node2vec), PyTorch + PyTorch Geometric (HGT), sentence-transformers (multilingual-e5-small), scikit-learn (KMeans) |
| Backend | FastAPI, Pydantic, Uvicorn |
| Frontend | React 19, Vite, React Router, Vitest + Testing Library |
| Automation | GitHub Actions |
