# Component 3 Research Dataset Preparation

Code: [`research/component_3/preprocessing/research_dataset.py`](../../research/component_3/preprocessing/research_dataset.py), research snapshots in [`shared/utils/snapshots.py`](../../shared/utils/snapshots.py), extraction in [`shared/database/snapshot_export.py`](../../shared/database/snapshot_export.py)
Tests: [`tests/component_3/test_research_dataset.py`](../../tests/component_3/test_research_dataset.py)

This step is the boundary between **raw/current collection data** and **research-ready analytical data**. It prepares the clean input for the later heterogeneous commenter–video–channel–topic graph. It computes **no** graph, embedding, diffusion or score.

## Workflow

```
Supabase PostgreSQL      current shared data (collectors write here)
        │  export_research_snapshot  (one REPEATABLE READ, READ ONLY transaction = consistent extraction point)
        ▼
Research snapshot        data/snapshots/research/rs-<YYYYMMDDTHHMMSSZ>/   immutable Parquet + _snapshot.json
        │  DuckDB views over the Parquet files (nothing copied into a permanent database)
        ▼
Validation               STEP 07 quality checks + research-level checks  →  _research_report.json
        │  only if research-ready
        ▼
Research-ready dataset   data/processed/component_3/<snapshot_id>/*.parquet
        ▼
Heterogeneous graph      see hetero_graph.md (STEP 13)
```

| Layer | Role here |
|---|---|
| Supabase | Current shared data: the source of the extraction |
| Parquet | The immutable research snapshot (raw, as extracted) and the research-ready datasets |
| DuckDB | All transformations and checks, as SQL over Parquet |

```powershell
python -m research.component_3.preprocessing.research_dataset --extract     # new snapshot from Supabase, then prepare
python -m research.component_3.preprocessing.research_dataset               # prepare the latest snapshot
python -m research.component_3.preprocessing.research_dataset --snapshot rs-20261008T093000Z --no-export
```
Exit code: `0` research-ready · `1` not research-ready (see report) · `2` error.

## Research snapshots

These extend the STEP 06 snapshot system, using the same manifest format, SHA-256 checksums and immutability:

| | Day snapshot (STEP 06) | Research snapshot |
|---|---|---|
| Contents | Observations collected on one UTC day | **Full current dataset** at one extraction point |
| Location | `data/snapshots/<YYYY-MM-DD>/` | `data/snapshots/research/rs-<timestamp>/` |
| Written | Incrementally, then sealed | **Once**, through a staging folder renamed into place |
| In `*_history` views | Yes | No |

The manifest records:
- the snapshot ID, `created_at`, and `extracted_at` (time of the database read)
- the source (`supabase_postgresql`) and isolation level
- the schema version and storage format
- for each dataset: row and unique-ID counts, columns, `collected_at` range, SHA-256

It contains no secrets.

- Data is **stored as extracted**, so duplicates or broken references stay visible to validation.
- The one exception is privacy: a snapshot containing commenter IDs that aren't pseudonyms is **refused** and nothing is written.
- `prepare()` refuses to analyse a snapshot whose files no longer match their checksums.

## Validation and the data-quality report

`prepare(snapshot_id)` runs:
1. **STEP 07 quality checks** on the three datasets, one row per ID (`validate_files`).
2. **Research-level checks.** In a full snapshot these are **errors**, even where STEP 07 only warns:

| Check | Rule |
|---|---|
| `duplicate_<entity>` | Duplicate `channel_id` / `video_id` / `comment_id` rows (exact and conflicting are reported separately) |
| `missing_<entity>_<field>` | A required schema field is missing |
| `orphan_videos` | Video's channel not in the snapshot |
| `orphan_comments` | Comment's video not in the snapshot |
| `comments_without_channel` | Comment's channel not in the snapshot |
| `orphan_replies` | Reply's parent comment not in the snapshot |
| `invalid_reply_links` | Reply on a different video than its parent, or replying to itself |
| `comment_channel_mismatch` | Comment's `channel_id` differs from its video's channel |
| `unpseudonymized_commenter_ids` | A commenter ID isn't a pseudonym (values are never shown) |
| `empty_dataset` | No channels or no videos |

**Research-ready** means the STEP 07 status isn't `INVALID` and no research-level error exists. Nothing is repaired, deduplicated or filled in. Problems are reported and the export is withheld.

**Missing values:**
- **Invalid missing** values are required fields that are empty; they're counted under `missing_required`.
- **Valid nulls** are optional fields: for example hidden likes, disabled comment counts, never-edited comments, and comments without a commenter ID. They're counted under `valid_nulls` and aren't problems.

The report is saved as `_research_report.json` next to the snapshot (derived metadata), and printed:

- **Counts:** channels, videos, comments (top-level and replies), unique commenters.
- **Duplicates:** duplicate rows and conflicting IDs per entity.
- **Missing required values** and valid nulls.
- **Relationships:** valid video→channel, comment→video, comment→channel and reply→parent links.
- **Cross-channel readiness:**
  - commenters on one channel vs on 2+ channels
  - channels with commenters
  - comments without a commenter ID
  - channel pairs with overlap, and the top pairs

These are **descriptive data-quality statistics, not research findings.**

## Research-ready datasets

DuckDB views, ordered deterministically and exported as Parquet when the snapshot is research-ready:

| Dataset | One row per | Main columns |
|---|---|---|
| `channel_dataset` | Channel | Channel fields, `stored_videos`, `stored_comments` |
| `video_dataset` | Video | Video fields (all timestamps), `channel_name` |
| `comment_dataset` | Comment | `commenter_id` (pseudonym), `parent_comment_id`, `is_reply`, text, likes, `published_at`, `edited_at`, `collected_at` |
| `commenter_participation` | Commenter × channel × video | `comment_count`, `reply_count`, `first_comment_at`, `last_comment_at` |
| `commenter_channels` | Commenter | `channel_count`, `video_count`, `comment_count`, first and last comment |
| `channel_commenters` | Channel | `unique_commenters`, `commenters_also_on_other_channels` |
| `channel_pair_overlap` | Channel pair (`channel_a < channel_b`) | `shared_commenters` |

Event-level timestamps (`published_at`, `edited_at`, `collected_at`) are kept in `comment_dataset` and `video_dataset` for later temporal analysis. Aggregates sit alongside them and never replace them.

```python
from research.component_3.preprocessing import research_dataset as rd
with rd.research_session("rs-20261008T093000Z") as con:
    overlap = rd.query(con, "channel_pair_overlap")
    participation = rd.query(con, "commenter_participation")
```

## Privacy and interpretation

- Commenters appear **only** as pseudonyms (`commenter_id` = `anon_` + HMAC-SHA256; see [privacy.md](privacy.md)). Raw commenter IDs are not in Supabase, snapshots, research datasets, reports or logs, and a snapshot with raw IDs is refused.
- A shared commenter between two channels is an **observable interaction signal**. It doesn't show audience migration, subscription, real-world identity, influence or causality, and the pipeline infers none of these.
