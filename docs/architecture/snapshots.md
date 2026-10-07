# Research Snapshots

Code: [`shared/utils/snapshots.py`](../../shared/utils/snapshots.py) · Tests: [`tests/shared/test_snapshots.py`](../../tests/shared/test_snapshots.py)
Builds on: [dataset_storage.md](dataset_storage.md) (how data enters snapshots) · [analytics.md](analytics.md) (querying)

## What a research snapshot is

A **research snapshot** is the set of YouTube data our system collected on one UTC day, frozen once collection for that day is finished. It holds every channel, video and comment observation made that day, plus a small manifest describing it.

## Why snapshots are needed

| Need | How snapshots help |
|---|---|
| **Temporal analysis** | Metrics such as views and subscribers change over time; each snapshot records them at a known date |
| **Historical comparison** | Two snapshots can be compared directly, e.g. a video's views on 2026-10-07 vs 2026-10-14 |
| **Reproducible experiments** | An experiment names the snapshot(s) it used; sealed snapshots never change, so the same input gives the same result |
| **Model evaluation** | Train on earlier snapshots and evaluate on later ones without information leaking backwards |
| **Data recovery** | The latest tables can be rebuilt from the snapshots, and checksums show whether a file was damaged |

## Naming convention

```
data/snapshots/
├── 2026-10-07/                 ← snapshot_id = UTC date of collected_at
│   ├── channels.parquet
│   ├── videos.parquet
│   ├── comments.parquet
│   └── _snapshot.json          ← manifest; present only when the snapshot is complete
└── 2026-10-08/
```

- `snapshot_id` is the date **`YYYY-MM-DD` in UTC**, taken from each record's `collected_at` (not `published_at`).
- This is the folder layout `store_records` already uses (STEP 04). Snapshot management adds validation, sealing and listing on top; it doesn't create a second structure.
- Folders whose names aren't dates are ignored.

## Life cycle

```
collection runs (store_records)        create_snapshot(day)             reopen_snapshot(day, confirm=True)
───────────────────────────────►  incomplete  ───────────────►  complete  ─────────────────────────────►  incomplete
   observations appended            (no manifest)   validate + seal   (immutable)   deliberate, explicit only
```

| Status | Meaning |
|---|---|
| `incomplete` | Data is being collected for that day; no manifest. Not used for research by default. |
| `complete` | Validated and sealed. **Immutable:** `store_records` refuses to write to it. |
| `invalid` | Manifest unreadable, or a sealed file is missing. Needs investigation. |

## Creating a snapshot

After the last collection run of a day:

```python
from shared.utils import snapshots

info = snapshots.create_snapshot("2026-10-07")
print(info.status, info.row_counts)       # complete {'channels': .., 'videos': .., 'comments': ..}
```

`create_snapshot`:
1. Refuses if the snapshot is already complete (`SnapshotExistsError`), unless `replace=True`.
2. **Validates** every dataset (see below). On any problem it raises `SnapshotValidationError` listing **all** problems, and writes nothing.
3. Writes the manifest **last and atomically** (temp file, then rename). If anything fails part-way, no manifest exists, so the snapshot stays `incomplete`, never falsely `complete`. The temp file is removed.

By default all three datasets are required. If a day deliberately has no comments, pass `required=["channels", "videos"]`; this choice is recorded in the manifest.

### Validation checks
- Every required dataset file exists, and any other dataset present is validated too.
- Each Parquet file can be opened and has exactly the schema columns (`shared.schemas`).
- No required field is missing, and no ID is empty.
- Every `collected_at` falls on the snapshot's UTC date.
- There are no duplicate (ID, `collected_at`) rows, and no negative counts.
- Row counts are recorded.

## Metadata (`_snapshot.json`)

```json
{
  "manifest_version": 1,
  "snapshot_id": "2026-10-07",
  "created_at": "2026-10-07T23:05:00Z",
  "source": "youtube_data_api",
  "schema_version": "1.0",
  "storage_format": "parquet",
  "required_datasets": ["channels", "comments", "videos"],
  "datasets": {
    "videos": {
      "file": "videos.parquet", "rows": 240, "unique_ids": 240,
      "columns": ["video_id", "..."],
      "collected_at_min": "2026-10-07T02:00:00Z", "collected_at_max": "2026-10-07T02:40:00Z",
      "sha256": "…"
    }
  }
}
```

The manifest contains **no** API keys, tokens, salts, credentials or commenter identifiers. It holds only counts, times, column names and checksums.

## Listing and retrieving

```python
from shared.utils import snapshots

snapshots.list_snapshots()                      # all, oldest first, with status
snapshots.list_snapshots(status="complete")
snapshots.latest_snapshot()                     # newest complete snapshot
snapshots.get_snapshot("2026-10-07")            # SnapshotInfo: status, datasets, row_counts, created_at
snapshots.snapshot_exists("2026-10-07")         # True only if complete
snapshots.read_snapshot_dataset("2026-10-07", "videos")   # DataFrame (complete snapshots only by default)
```

### Querying a snapshot with DuckDB

```python
from shared.utils import analytics, snapshots

with snapshots.snapshot_session("2026-10-07") as con:   # views: channels, videos, comments
    analytics.channel_summary(con=con)                  # any analytics function works on a snapshot
    con.sql("SELECT count(*) FROM comments").show()
```

DuckDB reads the snapshot's Parquet files directly; no other database is involved. To look across all days, use the `*_history` views from `analytics.research_session()`.

A snapshot holds only what was **collected that day**. A video not re-collected that day won't appear in it. The full known state at a date is in the history: the latest observation per ID with `collected_at` up to that date.

## Immutability

| Action | Result |
|---|---|
| `create_snapshot` on a complete snapshot | `SnapshotExistsError`; needs `replace=True` |
| `store_records` with data for a sealed day | `SnapshotImmutableError`; nothing is written, including the latest tables |
| Collecting data for a **new** day | Allowed |
| Changing a sealed snapshot on purpose | `reopen_snapshot(day, confirm=True)`, then store the correction, then `create_snapshot(day, replace=True)` |
| A file edited outside the storage layer | `verify_snapshot(day)` reports a checksum mismatch |

Re-sealing records a new `created_at`. Note any deliberate correction in your experiment log, because results computed before the correction used the old data.

## Errors

| Error | When |
|---|---|
| `SnapshotNotFoundError` | No folder for that date, or no complete snapshot exists (`latest_snapshot`) |
| `SnapshotExistsError` | Already sealed (and `replace=True` not given), or `reopen_snapshot` without `confirm=True` |
| `SnapshotValidationError` | Validation failed; `.errors` lists every problem. Also raised when reading an incomplete snapshot without opting in |
| `SnapshotImmutableError` | `store_records` tried to change a sealed day |
| `ValueError` | Malformed snapshot ID, source or `required` list |

## Not covered here

Collecting data, scheduling snapshot creation, retention and deletion of old snapshots, and temporal research methods are later steps. The 30-day retention question (see [data_layer.md](data_layer.md)) applies to snapshots and must be decided before real data is kept.
