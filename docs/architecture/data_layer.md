# Shared Research Data Layer

Status: **storage infrastructure implemented** (STEP 02): data-path configuration, Parquet storage and DuckDB query utilities in `shared/utils/`, with tests in `tests/shared/`.
Shared schemas implemented in STEP 03 (`shared/schemas/`, see [schemas.md](schemas.md)).
Schema → Parquet dataset storage implemented in STEP 04 (`shared/utils/datasets.py`, see [dataset_storage.md](dataset_storage.md)).
DuckDB analytical query layer implemented in STEP 05 (`shared/utils/analytics.py`, see [analytics.md](analytics.md)).
Research snapshot management implemented in STEP 06 (`shared/utils/snapshots.py`, see [snapshots.md](snapshots.md)).
Data validation and quality checks implemented in STEP 07 (`shared/utils/quality.py`, see [data_quality.md](data_quality.md)).
YouTube Data API v3 client implemented in STEP 08 (`shared/data_collection/youtube_client.py`, see [youtube_api.md](youtube_api.md)).
Commenter pseudonymization implemented (`shared/utils/privacy.py`, see [privacy.md](privacy.md)).
**Not implemented yet:** the YouTube collectors (channels, videos, comments) and all component research logic.

## Purpose

All four components read from one shared, versioned set of YouTube data instead of each collecting their own. This keeps experiments **reproducible**, avoids spending the API quota twice, and lets results from different components be compared on the same snapshot.

## Architecture

```
YouTube Data API v3          external source (public data only)
        │
        ▼
Collection Pipeline          shared/data_collection/ — periodic, incremental collection (future)
        │
        ▼
Raw Data                     data/raw/ — API responses as received, never edited
        │
        ▼
Parquet                      data/snapshots/ — normalised tables, one partition per snapshot
        │
        ▼
DuckDB                       analytical query engine over the Parquet files (not the source of truth)
        │
        ▼
Shared Research Data         common tables / views defined in shared/schemas/
        │
        ▼
Research Components          C1 · C2 · C3 · C4  →  data/processed/component_N/
```

| Layer | Location | Format | Written by | Notes |
|---|---|---|---|---|
| Raw | `data/raw/` | API responses (e.g. JSON Lines) | Collection pipeline | Immutable, append-only; kept for re-processing and audit |
| Snapshots | `data/snapshots/<YYYY-MM-DD>/` | Parquet, one folder per UTC date of `collected_at` | `store_records` | Every observation; the single source of truth for research |
| Query engine | `DUCKDB_PATH` (default `data/research.duckdb`) | DuckDB | Rebuilt from Parquet | Holds views only; safe to delete and rebuild |
| Features | `data/features/` | Parquet | Feature-engineering steps | Model-ready features derived from snapshots |
| Latest datasets | `data/processed/<dataset>.parquet` | Parquet | `store_records` | One row per ID (newest `collected_at`) for channels, videos, comments |
| Processed | `data/processed/component_N/` | Parquet | Each component | Component-specific outputs |

All of `data/` and `*.duckdb` are git-ignored.

## Parquet is the source of truth; DuckDB is the query engine

| | Parquet | DuckDB |
|---|---|---|
| Role | **Persistent research dataset** | **Analytical query engine** |
| Holds | All shared and component data | Views, temporary and scratch tables only |
| If deleted | Data is lost (re-collect from the API) | Nothing is lost; rebuild from Parquet |
| Versioned by | Snapshot folder (`snapshot_date`) | Not versioned |

Rules: every dataset that matters is written to Parquet with `write_dataset`. Never keep data *only* inside the `.duckdb` file.

### Why Parquet?
- **Efficient analytical storage:** compressed, so large comment and statistics tables stay small on disk.
- **Column-oriented:** queries read only the columns they need.
- **Suits large research datasets:** files can be split by snapshot and read together.
- **Works with the Python data-science stack:** pandas, pyarrow, DuckDB, scikit-learn pipelines.
- **Typed:** integers, nullable values and UTC timestamps keep their types across machines.
- **Reproducible snapshots:** one immutable folder per collection date.

### Why DuckDB?
- **Analytical SQL engine** built for aggregations, joins and window functions.
- **Queries Parquet directly**, without importing it first.
- **Lightweight:** a single pip package that runs in-process.
- **No database server** to install, run or share passwords for.
- **Suits research analytics** on a laptop, with results returned as pandas DataFrames.

A server database (PostgreSQL, MySQL, MongoDB) is **not required at this stage**. One can be added later behind the backend API if the dashboard needs it.

## Data principles

| Principle | How the design supports it |
|---|---|
| Reproducibility | Experiments reference a fixed `snapshot_date`; raw data is never overwritten |
| Historical snapshots | Each collection run writes a new Parquet partition |
| Analytical queries | DuckDB SQL over all snapshots at once |
| Shared datasets | One schema in `shared/schemas/`, used by all components |
| Incremental collection | Only new or changed videos and comments are fetched per run |
| Near-real-time refresh | Collection can be scheduled more often (e.g. daily) without design changes |
| Raw vs processed separation | `raw/` → `snapshots/` → `processed/component_N/` |

YouTube Data API v3 is a request/response API with a daily quota, **not a streaming API**. "Near-real-time" here means frequent periodic collection, limited by the quota.

## Historical snapshots

Each collection run writes into its own dated folder, and earlier snapshots are never overwritten:

```
data/snapshots/
├── 2026-10-07/
│   ├── channels.parquet
│   ├── videos.parquet
│   └── comments.parquet
├── 2026-10-08/
└── 2026-10-09/
```

`snapshot_dir("2026-10-07")` returns the folder for one date. `query_parquet("data/snapshots")` queries every snapshot at once, and `query_parquet("data/snapshots/*/videos.parquet")` queries one table across all dates. Automatic snapshot collection is not implemented yet.

## Using the storage layer

```python
from shared.utils import (
    component_dir, query, query_parquet, read_dataset, snapshot_dir, write_dataset,
)

# Write / read Parquet (relative paths are taken from the project root)
write_dataset(df, snapshot_dir("2026-10-07") / "videos.parquet")
write_dataset(df, component_dir(3) / "bridge_scores.parquet", overwrite=True)
videos = read_dataset("data/snapshots/2026-10-07/videos.parquet")

# Query one Parquet file / folder / glob; it is available as the view `dataset`
top = query_parquet(
    "data/snapshots/*/videos.parquet",
    "SELECT channel_id, sum(view_count) AS views FROM dataset GROUP BY channel_id",
)

# Free SQL; relative paths in SQL also resolve from the project root
n = query("SELECT count(*) AS n FROM 'data/processed/component_3/bridge_scores.parquet'")
```

| Module | Main functions |
|---|---|
| `shared/utils/paths.py` | `get_data_paths`, `resolve_path`, `snapshot_dir`, `component_dir` |
| `shared/utils/parquet_io.py` | `write_dataset`, `read_dataset`, `dataset_exists` |
| `shared/utils/duckdb_query.py` | `connect`, `duckdb_connection`, `query`, `query_parquet` |

Behaviour:
- **Paths:** relative paths resolve from the repository root, never from the current working directory, so notebooks in any folder work. No absolute paths are hard-coded.
- **Writing:** parent folders are created automatically. An existing file is only replaced with `overwrite=True`, and the replacement is atomic.
- **Schema:** column names must be unique strings. `required_columns=[...]` rejects a DataFrame that lacks expected columns.
- **Timestamps:** stored in **UTC**. Zoned values are converted to UTC, and naive values are assumed to already be UTC. DuckDB sessions also run in UTC.
- **Missing values:** nullable integers (`Int64`), strings and floats keep their nulls.
- **Errors:** a missing dataset raises `DatasetNotFoundError` (a `FileNotFoundError`); a bad DataFrame raises `SchemaError`.
- **DuckDB:** `query_parquet` runs in memory and never locks the database file; `query` and `connect` use `DUCKDB_PATH`.

Tests: `python -m pytest`. They use a tiny synthetic **TEST DATA** set (`tests/shared/conftest.py`) and a temporary folder, never the real `data/`.

## Core entities

Implemented in `shared/schemas/` (STEP 03): **Channel**, **Video** and **Comment**. Fields, validation, privacy notes and types are in [schemas.md](schemas.md). Use `to_dataframe(records, Model)` before `write_dataset` so every snapshot has the same Parquet schema.

Planned later: `video_stats` (per-snapshot metrics, if separated from videos), `collection_runs` (run metadata), (commenter IDs are pseudonymized on storage, see [privacy.md](privacy.md)).

## Use by component

| Component | Main tables used |
|---|---|
| C1 — Growth Opportunity Prediction | channels, videos, video_stats |
| C2 — Audience Demand and Content Gap | videos, comments |
| C3 — Audience Bridge Scoring | comments (hashed commenter IDs), videos, channels; C2 topic outputs |
| C4 — Emerging Topic Detection | videos, comments, across snapshots |

## Open decisions

- **Retention vs. history:** the project follows a 30-day retention rule (see `data/README.md`) based on the YouTube API Services policies, while research needs historical snapshots. The team must agree which fields can be kept beyond 30 days (e.g. aggregated, de-identified statistics) and which must be refreshed or deleted.
- **Snapshot frequency:** weekly (current plan) or more often, depending on quota.
- **Channel list:** the target and sister channels go in `config/`.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `DATA_DIR` | `data` | Root of the data folders |
| `DUCKDB_PATH` | `data/research.duckdb` | DuckDB database file |
| `YOUTUBE_API_KEY` | — | API key (in `.env` only) |
| `COMMENTER_HASH_SALT` | — | Salt for hashing commenter IDs (in `.env` only) |
