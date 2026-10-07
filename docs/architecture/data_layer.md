# Shared Research Data Layer

Status: **design only.** Nothing described here is implemented yet.

## Purpose

All four components read from one shared, versioned set of YouTube data instead of each collecting their own. This keeps experiments **reproducible**, avoids spending the API quota twice, and lets results from different components be compared on the same snapshot.

## Architecture

```
YouTube Data API v3          external source (public data only)
        │
        ▼
Collection Pipeline          shared/data_collection/ — periodic, incremental collection
        │
        ▼
Raw Data                     data/raw/ — API responses as received, never edited
        │
        ▼
Parquet                      data/snapshots/ — normalised tables, one partition per snapshot
        │
        ▼
DuckDB                       analytical query engine over the Parquet files
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
| Snapshots | `data/snapshots/` | Parquet, partitioned by `snapshot_date` | Normalisation step | The single source of truth for research |
| Query engine | `DUCKDB_PATH` (default `data/research.duckdb`) | DuckDB | Rebuilt from Parquet | Holds views only; safe to delete and rebuild |
| Processed | `data/processed/component_N/` | Parquet | Each component | Component-specific features and outputs |

All of `data/` and `*.duckdb` are git-ignored.

## Why Parquet + DuckDB

- **Parquet** is columnar, compressed and typed, works well with pandas and pyarrow, and its files are easy to version per snapshot.
- **DuckDB** runs in-process (no server) and queries Parquet directly with SQL, which suits a research team working on laptops.
- A server database (PostgreSQL, MySQL, MongoDB) is **not required at this stage**. One can be added later behind the backend API if the dashboard needs it.

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

## Core entities (to be defined in `shared/schemas/`)

`channels` · `videos` · `video_stats` (per snapshot) · `comments` (commenter IDs hashed with `COMMENTER_HASH_SALT`) · `collection_runs` (run metadata)

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
