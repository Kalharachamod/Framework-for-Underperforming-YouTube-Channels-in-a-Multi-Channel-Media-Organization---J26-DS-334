# Research Dataset Storage

Code: [`shared/utils/datasets.py`](../../shared/utils/datasets.py) · Tests: [`tests/shared/test_datasets.py`](../../tests/shared/test_datasets.py)
Builds on: [data_layer.md](data_layer.md) (Parquet + DuckDB) and [schemas.md](schemas.md) (Channel, Video, Comment).

This layer stores validated Channel, Video and Comment records as Parquet. It is storage infrastructure, not a research method.

## Flow

```
Channel / Video / Comment records  (schema instances or dicts)
        │  store_records("videos", records)
        ▼
Validation (shared.schemas) ── invalid record or conflicting duplicate → error, nothing written
        ▼
Typed table (to_dataframe)
        ├──► Snapshot (history)   data/snapshots/<YYYY-MM-DD>/videos.parquet   append-only
        └──► Latest (current)     data/processed/videos.parquet               one row per video_id
        ▼
DuckDB views: videos, videos_history, ...  (create_views)
```

## Two forms of every dataset

| | Snapshot (history) | Latest (current state) |
|---|---|---|
| Location | `data/snapshots/<YYYY-MM-DD>/<dataset>.parquet` | `data/processed/<dataset>.parquet` |
| Rows | **Every observation** | **One row per ID** |
| Identity | (`id`, `collected_at`) | `id` |
| On a new observation | Added; older observations are kept | Replaced if the new one has a newer `collected_at` |
| Used for | Temporal research, growth over time, reproducibility | "What do we know now", joins, dashboards |

The datasets and their IDs:

| Dataset | Schema | ID |
|---|---|---|
| `channels` | `Channel` | `channel_id` |
| `videos` | `Video` | `video_id` |
| `comments` | `Comment` | `comment_id` |

## `collected_at` vs `published_at`

| Field | Meaning | Set by | Used for |
|---|---|---|---|
| `published_at` | When **YouTube** published the video or comment | YouTube | Content age, publication trends |
| `collected_at` | When **our system observed** the record | The collector | Which observation is newer; which snapshot folder |

The same video collected on three days gives three observations with the same `published_at` and three different `collected_at` values and metrics. All three are kept in the snapshots. `published_at` never decides storage order or snapshot placement.

## Duplicates and updates

The rules are deterministic, so the same input always gives the same files:

| Situation | Behaviour |
|---|---|
| The same record twice in one batch (identical) | Stored once |
| Two **different** records with the same ID and same `collected_at` in one batch | **`DuplicateRecordError`**; nothing is written. One observation can't have two values. |
| The same ID with a **newer** `collected_at` | Snapshot: added as a new observation. Latest: **replaces** the older row (e.g. updated view counts). |
| The same ID with an **older** `collected_at` (late or back-filled data) | Snapshot: added to its own date. Latest: **not** replaced, because newer data wins. |
| The same ID and same `collected_at` as already stored (a re-run) | Treated as a correction: replaces that one observation |
| Records whose ID isn't in the batch | Untouched |

Updates are never discarded silently. Every observation stays in the snapshots, even when the latest table only keeps the newest. `store_records` returns a `StoreSummary` with `received`, `snapshot_rows_added`, `latest_inserted` and `latest_updated`, so collectors can log what happened.

## Incremental collection

A future collector only needs to do this:

```python
from shared.schemas import Video
from shared.utils import store_records

videos = [Video(**parse(item)) for item in api_items]   # or plain dicts
summary = store_records("videos", videos)
print(summary.latest_inserted, summary.latest_updated, summary.snapshot_rows_added)
```

- Each run adds new records and updates changed ones. Records from earlier runs are kept.
- Re-running the same batch is safe and produces the same files.
- Each write replaces files atomically, so a crash never leaves a half-written file.
- **Single writer:** run one collector at a time. Concurrent writers to the same dataset are not supported.

## Snapshots

```
data/snapshots/
├── 2026-10-07/  channels.parquet  videos.parquet  comments.parquet
├── 2026-10-08/  ...
└── 2026-10-09/  ...
```

- The folder is the **UTC date of `collected_at`**. A run that crosses midnight UTC is split across two folders.
- Storing new data only rewrites the folder for that data's date. Other dates are never touched.
- Two runs on the same day are both kept in that day's file, with different `collected_at` values.
- To reproduce an analysis, record which snapshot dates it used.
- When a day's collection is finished, seal it with `create_snapshot(day)`. After that, `store_records` refuses to write to that day (`SnapshotImmutableError`). See [snapshots.md](snapshots.md).

## Reading

| Function | Returns |
|---|---|
| `read_latest("videos")` | Current state, one row per ID |
| `read_snapshot("videos", "2026-10-07")` | One day's observations |
| `read_history("videos")` | All observations across snapshots, ordered by `collected_at` |

Results have the schema's column order and types: `string`, nullable `Int64`, UTC timestamps, and tags as list values (use `list(v)`).

## DuckDB

For ready-made, parameterized queries (lookups, filters, joins, summaries), use the analytical query layer in [analytics.md](analytics.md). The views below are what it builds on.

```python
from shared.utils import create_views, duckdb_connection

with duckdb_connection() as con:          # data/research.duckdb
    create_views(con)                     # videos, videos_history, channels, ...
    con.sql("""
        SELECT channel_id, count(*) AS videos, CAST(sum(view_count) AS BIGINT) AS views
        FROM videos GROUP BY channel_id
    """).show()
    con.sql("SELECT collected_at, view_count FROM videos_history WHERE video_id = ? ORDER BY 1",
            params=["..."]).show()
```

- `<dataset>` views read the latest table; `<dataset>_history` views read every snapshot.
- Views only **read** Parquet; DuckDB stores no copy of the data.
- View definitions use project-relative paths, which resolve through `connect()`. Open the database through `shared.utils.connect`; an outside tool such as DBeaver doesn't know the project root.
- Views are created only for datasets that have files. Call `create_views` again after the first data arrives.
- Filter timestamps with time-zone literals, e.g. `WHERE collected_at >= TIMESTAMPTZ '2026-10-08 00:00:00+00'`.

## Errors

| Problem | Error |
|---|---|
| Invalid record, missing field, bad timestamp | `pydantic.ValidationError` (nothing written) |
| Conflicting versions of one observation | `DuplicateRecordError` (nothing written) |
| Unknown dataset name | `ValueError` |
| Wrong record type (e.g. Channel into `videos`) | `TypeError` |
| Stored file has different columns than the schema | `SchemaError` |
| Stored file is corrupted or not Parquet | `DatasetReadError` (checked before anything is written) |
| Dataset missing when reading | `DatasetNotFoundError` (a `FileNotFoundError`) |

## Privacy

Comments are stored with `author_channel_id` exactly as validated by the schema; this layer does no hashing. Hashing commenter IDs is a separate step, which must happen before real comment data is collected and stored.
