# Shared Research Data Schemas

Schema version: **1.0** (`shared.schemas.SCHEMA_VERSION`)
Code: [`shared/schemas/`](../../shared/schemas/) · Tests: [`tests/shared/test_schemas.py`](../../tests/shared/test_schemas.py)

These are **shared research schemas**: they define what a channel, video or comment record looks like and reject obviously invalid data. They are **not research algorithms**. They contain no scoring, prediction, topic modelling, graph or privacy logic.

## Where schemas sit

```
YouTube API response
        ↓
Collector / parser          (future step: maps API JSON to schema fields)
        ↓
Shared schema               Channel · Video · Comment   (validation)
        ↓
to_dataframe(...)           typed pandas DataFrame
        ↓
write_dataset(...)          Parquet  (source of truth)
        ↓
query / query_parquet       DuckDB   (analysis)
        ↓
Research components
```

The schemas do not depend on the YouTube API client. A collector builds them from API responses, and they can equally be built from test data or from Parquet rows.

## Conventions

| Topic | Rule |
|---|---|
| IDs | Strings, 1–128 characters of letters, digits, `-`, `_` or `.`; surrounding spaces are trimmed. Empty IDs, spaces or slashes inside, and non-strings are rejected. The `UC…` channel prefix is **not** enforced. |
| Counts | Integers `>= 0`, or `None` when unavailable. Zero is valid. Numeric strings such as `"1200"` are accepted, because the API returns statistics as strings. Negative numbers, fractions, booleans and text are rejected. |
| Timestamps | Must include a time zone, and are converted to **UTC**. Naive timestamps and invalid dates are rejected. |
| Tags | Always a list of strings. A missing value becomes `[]`, whitespace is trimmed and empty tags are dropped. A single string such as `"a,b"` or non-string items are rejected. |
| Text | Titles and comment text are stored exactly as given (unicode, HTML and whitespace kept); they may be empty. |
| Unknown fields | Rejected, so typos are caught early. |
| Records | Immutable once created. |

## Channel

| Field | Type | Required | Notes |
|---|---|---|---|
| `channel_id` | string ID | yes | |
| `channel_name` | string | yes | non-empty |
| `subscriber_count` | int ≥ 0 | no | `None` when hidden |
| `view_count` | int ≥ 0 | no | |
| `video_count` | int ≥ 0 | no | |
| `collected_at` | UTC timestamp | yes | when the collector fetched it |

## Video

| Field | Type | Required | Notes |
|---|---|---|---|
| `video_id` | string ID | yes | |
| `channel_id` | string ID | yes | uploading channel |
| `title` | string | yes | may be empty |
| `description` | string | no | |
| `published_at` | UTC timestamp | yes | always returned by the API |
| `tags` | list of strings | no | `[]` when there are none |
| `view_count` | int ≥ 0 | no | |
| `like_count` | int ≥ 0 | no | `None` when likes are hidden |
| `comment_count` | int ≥ 0 | no | `None` when comments are disabled |
| `collected_at` | UTC timestamp | yes | |

## Comment

| Field | Type | Required | Notes |
|---|---|---|---|
| `comment_id` | string ID | yes | reply IDs (`parent.reply`) allowed |
| `video_id` | string ID | yes | |
| `channel_id` | string ID | yes | channel that owns the video |
| `author_channel_id` | string ID | no | see Privacy |
| `comment_text` | string | yes | may be empty |
| `published_at` | UTC timestamp | yes | |
| `like_count` | int ≥ 0 | no | |
| `collected_at` | UTC timestamp | yes | |

## Privacy

- `author_channel_id` is a **publicly observable platform identifier**, when YouTube returns it. It is optional: a missing value stays `None` and is **never replaced with placeholder data**.
- Its presence does **not** prove subscriber status, audience migration, demographic identity or causality.
- The schema holds the value as given (in memory). `store_records` replaces it with a pseudonym (HMAC with `COMMENTER_HASH_SALT`) before anything is stored; see [privacy.md](privacy.md).
- The field is hidden from `repr()` and `str()`, so it doesn't appear in logs or error messages by accident.
- Test data uses invented IDs only (`test_author_1`).

## Serialization

| Method | Output | Use |
|---|---|---|
| `record.to_record()` | dict, datetimes as `datetime` | pandas / Parquet |
| `record.to_json_dict()` | dict, ISO-8601 strings | future API responses |
| `to_dataframe(records, Model)` | typed DataFrame | `write_dataset` |

```python
from shared.schemas import Video, to_dataframe
from shared.utils import snapshot_dir, write_dataset, query_parquet

videos = [Video(**parsed) for parsed in parsed_api_items]   # validation happens here
write_dataset(to_dataframe(videos, Video), snapshot_dir("2026-10-07") / "videos.parquet")
# Usually use store_records("videos", videos) instead: snapshots + latest + duplicates
# (see dataset_storage.md)
query_parquet("data/snapshots/*/videos.parquet", "SELECT channel_id, count(*) FROM dataset GROUP BY 1")
```

## Parquet and DuckDB types

`to_dataframe` gives every column a fixed type, so every snapshot of an entity has the **same Parquet schema**, even when an optional column is completely empty:

| Schema type | pandas | Parquet | DuckDB |
|---|---|---|---|
| ID / text | `string` | string | `VARCHAR` |
| Count | `Int64` (nullable) | int64 | `BIGINT` |
| Timestamp | `datetime64[us, UTC]` | timestamp (UTC) | `TIMESTAMP WITH TIME ZONE` |
| Tags | `list<string>` (Arrow) | list<string> | `VARCHAR[]` (use `unnest(tags)`) |

**Compatibility fix (STEP 03):** pandas can't read back a Parquet file that records a nested Arrow column type in its metadata. `write_dataset` now writes such columns as plain lists while keeping their exact Parquet type. This also stops an all-empty `tags` column being saved as `list<null>`. DataFrames without such columns are written exactly as before. When read back, `tags` values are array-like, so use `list(value)`.

## Evolving the schemas

- **Adding a field:** add it as optional with a default (`None` or `[]`) and add it to `DTYPES`. Older Parquet files remain readable. This is a minor version bump, e.g. `1.1`.
- **Renaming, removing or changing a type:** bump the major version (`2.0`) and note it here. Older snapshots keep their original columns.
- A test checks that `DTYPES` lists every model field in the same order.

## Assumptions

- `published_at` is always present for public videos and comments, so it is required.
- `collected_at` is set by the collector at fetch time.
- `channel_id` on a comment is the video owner's channel, which C3 needs for cross-channel links.
- Channel IDs are not checked for the `UC` prefix or a length of 24, to avoid rejecting valid edge cases.
