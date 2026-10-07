# DuckDB Analytical Query Layer

Code: [`shared/utils/analytics.py`](../../shared/utils/analytics.py) · Tests: [`tests/shared/test_analytics.py`](../../tests/shared/test_analytics.py)
Builds on: [data_layer.md](data_layer.md) · [schemas.md](schemas.md) · [dataset_storage.md](dataset_storage.md)

The common, read-only way for all components to query the shared research datasets. It provides **generic data access** (lookups, filters, joins, aggregates), not research methods.

## Where it sits

```
Parquet  (data/processed/*.parquet, data/snapshots/*/*.parquet)    ← written only by store_records
   ↓  DuckDB reads the files directly (no import, no copy)
DuckDB in-memory session with views: channels · videos · comments · *_history
   ↓  shared.utils.analytics  (parameterized queries → pandas DataFrames)
Future Component 3 stages: feature extraction → graph construction → GNN → diffusion → bridge scoring
```

## Why DuckDB

- **An analytical SQL engine:** fast joins, group-bys and window functions over columnar data.
- **Queries Parquet in place** with `read_parquet(...)`, so the data isn't duplicated into another store.
- **Embedded:** runs inside Python with no server, account or password (see [data_layer.md](data_layer.md)).
- **Returns pandas DataFrames directly**, which the research code already uses.

## How DuckDB queries Parquet

`research_session()` opens an **in-memory** DuckDB connection through `shared.utils.duckdb_query` (UTC session, project-relative paths) and creates views over the files:

| View | Reads | Rows |
|---|---|---|
| `channels`, `videos`, `comments` | `data/processed/<dataset>.parquet` | Latest observation per ID |
| `channels_history`, `videos_history`, `comments_history` | `data/snapshots/*/<dataset>.parquet` | Every observation |

The session is read-only in practice: it never writes Parquet and never opens `data/research.duckdb`. Parquet remains the source of truth.

## Available queries

Every function returns a **pandas DataFrame**. `to_records(df)` turns one into a list of dicts, with missing values as `None`.

| Area | Function | Notes |
|---|---|---|
| Channels | `get_channels()` | All channels |
| | `get_channel(channel_id)` | Empty if unknown |
| | `filter_channels(min_subscribers=, max_subscribers=, name_contains=, limit=)` | Hidden subscriber counts never match a count filter; `name_contains` is a case-insensitive literal match |
| | `count_channels()` | `int` |
| Videos | `get_channel_videos(channel_id, limit=)` | Newest published first |
| | `get_videos(start=, end=, date_field=, channel_id=, min_views=, limit=)` | Date-range filter |
| | `recent_videos(limit=10, channel_id=)` | |
| | `count_videos_by_channel()` | |
| | `channel_video_metrics()` | Summed views / likes / comment counts, plus `*_known` counts |
| Comments | `get_video_comments(video_id, limit=)` | Oldest first |
| | `get_channel_comments(channel_id, limit=)` | Through the comment → video → channel relationship |
| | `get_comments(start=, end=, date_field=, video_id=, limit=)` | Date-range filter |
| | `count_comments_by_video()` | Includes videos with 0 stored comments |
| | `count_comments_by_channel()` | Through videos |
| Cross-dataset | `channels_with_videos(channel_id=)` | One row per video, with channel name and subscribers |
| | `videos_with_comments(video_id=)` | One row per comment, with video and channel |
| | `channel_summary()` | Videos, views, likes, stored comments and engagement rate per channel |
| Custom | `run_query(sql, params)` | Your own parameterized SQL over the views |

**Counts and missing metrics:** "stored comments" counts the comments in our dataset. `comment_count` is YouTube's public total, so the two are kept separate. Hidden likes are `NULL`, never `0`. Sums skip them, and `*_known` columns show how many videos contributed.

**`engagement_rate`** in `channel_summary` is `(likes + comment_count) / views`, over videos where all three are known and views are above 0. It's `NULL` when it can't be computed. It's a descriptive statistic, **not** a research score.

## Dates

- Ranges filter on `published_at` (default) or `collected_at` via `date_field`. No other column is accepted.
- A `date` (or `"2026-10-07"`) means that **whole UTC day**, and both ends are inclusive.
- A `datetime` (or `"2026-10-07T10:00:00+05:30"`, or `...Z`) must include a time zone; it's converted to UTC.
- If `start` is after `end`, it's an error. The same day for both is allowed.

## Usage

```python
from shared.utils import analytics as a

a.count_channels()
a.get_videos(start="2026-10-01", end="2026-10-07", channel_id="UC...")
a.channel_summary()

# Several queries on one connection
with a.research_session() as con:
    videos = a.get_channel_videos("UC...", con=con)
    comments = a.get_channel_comments("UC...", con=con)
    growth = a.run_query(
        "SELECT collected_at, view_count FROM videos_history WHERE video_id = ? ORDER BY collected_at",
        ["..."], con=con,
    )
```

**For future components:** build features from these DataFrames, or from `run_query` SQL, instead of reading Parquet files by hand. For example, `videos_with_comments()` gives the comment–video–channel rows that Component 3's graph construction will need. If a query is used by more than one component, add it to `analytics.py` with a test, rather than copying SQL into notebooks.

## Safety and errors

- All user values (IDs, dates, thresholds, limits, search text) are bound as **SQL parameters (`?`)**. The only text placed into SQL is from fixed allow-lists (`date_field`) or fixed fragments (`LIMIT ?`).
- IDs are validated with the same rule as the schemas.

| Situation | Result |
|---|---|
| Unknown `channel_id` / `video_id`, or no matching rows | Empty DataFrame |
| Dataset never stored (no Parquet file) | `DatasetNotFoundError`, naming the missing dataset(s) and expected path |
| Stored but empty dataset | Empty DataFrame (`count_*` returns 0) |
| Invalid ID, date, date range, `date_field`, threshold or limit | `InvalidQueryParameter` (a `ValueError`) |
| Invalid SQL in `run_query` | DuckDB error, not hidden |

## Tests

```bash
python -m pytest tests/shared/test_analytics.py     # query layer only
python -m pytest                                    # everything
```

The tests store a small synthetic **TEST DATA** set with `store_records` in a temporary folder, and check exact, hand-calculated results. They never touch the real `data/` folder or call the YouTube API.
