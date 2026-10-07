# Data Validation and Quality Checks

Code: [`shared/utils/quality.py`](../../shared/utils/quality.py) · Tests: [`tests/shared/test_quality.py`](../../tests/shared/test_quality.py)
Builds on: [schemas.md](schemas.md) · [dataset_storage.md](dataset_storage.md) · [snapshots.md](snapshots.md)

## Why validation is required

Research results are only as reliable as their input. Collected data can contain problems: duplicates, broken references, impossible timestamps, negative counts, or files written with the wrong types. These would silently distort later stages such as graph construction and bridge scoring. The validation layer checks the shared datasets (**channels, videos, comments**) **before** they are used, and reports every problem in a structured, reproducible way.

## How it runs

The checks are SQL queries that **DuckDB runs directly on the Parquet files**; nothing is copied into another database, and large files aren't loaded into pandas. Two scopes:

| Scope | Files | Uniqueness rule |
|---|---|---|
| `validate_latest()` | `data/processed/<dataset>.parquet` | Each ID appears **once** |
| `validate_snapshot_quality(day)` | `data/snapshots/<day>/<dataset>.parquet` | Each (ID, `collected_at`) appears once; the same ID at different times is normal history |

## Validation categories

| Category | Checks | Severity |
|---|---|---|
| **dataset** | File missing or unreadable | error |
| | Dataset has no rows | warning |
| **schema** | Missing column; wrong type, compared with the STEP 03 schema (`VARCHAR`, `BIGINT`, `TIMESTAMP WITH TIME ZONE`, `VARCHAR[]`) | error |
| | Extra columns not in the schema | warning |
| **identifier** | Required ID missing; ID not matching the schema's ID rule | error |
| **duplicate** | Same ID (or ID + `collected_at`) with **different** values | error |
| | **Exact** duplicate rows (identical in every column) | warning |
| **relationship** | Comment's `channel_id` differs from its video's channel | error |
| | Video referencing a channel not in `channels` (orphan video); comment referencing a video not in `videos` (orphan comment) | warning |
| **timestamp** | Required timestamp missing; `published_at` after `collected_at`; `collected_at` in the future; snapshot row collected on another day | error |
| | `published_at` before YouTube existed (2005-04-23); comment published before its video | warning |
| **numeric** | Negative views, likes, comment counts, subscribers or video counts | error |
| | More likes than views (usually stale counts) | warning |
| **privacy** | Commenter IDs that look like raw YouTube channel IDs (hashing not yet applied) | warning |

**Nulls in optional fields are not problems.** Hidden likes and subscriber counts, or comments without an author ID, are legitimate API situations. They're reported only as `null_counts`.

**Orphans are warnings, not errors.** Incremental collection can legitimately hold a video before its channel's record, and one day's snapshot only contains what was collected that day. Orphans are reported with examples so the processing stage can decide what to do.

## Status

| Status | Meaning | Use for research? |
|---|---|---|
| `VALID` | No problems | Yes |
| `VALID_WITH_WARNINGS` | Usable; warnings should be reviewed (e.g. orphans, exact duplicates) | Yes, after review |
| `INVALID` | At least one error | **No**, not until fixed |

A run's overall status is the worst status among its datasets.

## Result format

`ValidationRun` → `results[dataset]` → `DatasetValidation`, which has:
- `status`, `total_rows`, `null_counts`
- `errors`, `warnings` (lists of `Issue`)
- `duplicate_count`, `relationship_violations`, `timestamp_violations`, `numeric_violations`

Each `Issue` has a `code` (e.g. `orphan_videos`), `severity`, `category`, `message`, `count` and up to 5 `examples` (public channel, video or comment IDs). `run.to_dict()` gives JSON, and `run.report()` gives a human-readable text report.

## Running validation

```powershell
python -m shared.utils.quality latest                 # validate the latest tables
python -m shared.utils.quality snapshot 2026-10-07    # validate a snapshot and save _quality.json
```
The exit code is `1` when the result is `INVALID`, so it can be used in scripts.

```python
from shared.utils import quality

run = quality.validate_latest()
print(run.status)            # Status.VALID / VALID_WITH_WARNINGS / INVALID
print(run.report())
videos = run.results["videos"]
videos.relationship_violations, [i.code for i in videos.errors]
```

Example report:
```
Data validation report - latest (2026-10-07T10:22:19Z)
Overall: INVALID

VIDEOS    INVALID   rows=3  errors=3 warnings=1 duplicates=1 relationship=1 timestamp=0 numeric=1
  ERROR [schema] column 'tags' has type INTEGER[], expected VARCHAR[]
  ERROR [duplicate] 1 video_id value(s) appear with different data (e.g. test_v1)
  ERROR [numeric] 1 negative 'view_count' value(s) (e.g. test_v1)
  WARN  [relationship] 1 video row(s) reference channels not in the channels dataset (e.g. test_v9)
```

## Integration with snapshots

```
store_records → create_snapshot (sealed, immutable) → validate_snapshot_quality → research-ready?
```

- `validate_snapshot_quality(day)` writes `data/snapshots/<day>/_quality.json`, with the full result plus the SHA-256 checksums of the files it validated.
- The quality file is **derived metadata**. It never changes the snapshot's data files or its `_snapshot.json` manifest, and it can be regenerated at any time.
- `is_research_ready(day)` is true only if **all** of these hold:
  1. The snapshot is complete (sealed).
  2. Its files are unchanged since sealing (`verify_snapshot`).
  3. A quality result exists and isn't `INVALID`.
  4. That result was produced for exactly the sealed files (checksums match).
- `latest_research_ready_snapshot()` returns the newest snapshot meeting all four, or `None`.

An `INVALID` snapshot is therefore never treated as research-ready, even though it's sealed.

## Why the system does not repair data automatically

The validator **detects and reports**; it never deletes duplicates, invents IDs, replaces timestamps or nulls, or changes metrics. Automatic repair would hide data problems from the researcher, make results depend on undocumented fixes, and could destroy information that matters, such as which of two conflicting values is correct. Repair decisions belong to a later, explicit and documented processing stage, so that every change to research data is intentional and reproducible.

## Privacy

Reports and quality files contain only counts, column names, check codes and public channel/video/comment IDs. They **never** contain comment text, commenter identifiers, API keys or other secrets. The privacy check only reports *how many* commenter IDs still look unhashed.
