# Supabase PostgreSQL: Shared Online Research Database

Code: [`shared/database/`](../../shared/database/) · Schema: [`migrations/0001_research_schema.sql`](../../shared/database/migrations/0001_research_schema.sql) · Tests: [`tests/shared/test_database.py`](../../tests/shared/test_database.py)

> Supabase is **infrastructure**, not the research contribution. The contribution is the proposed *Diffusion-Based Cross-Channel Audience Bridge Scoring* framework (heterogeneous commenter–video–channel–topic graph, metapath2vec / HGT, Personalized PageRank, topic similarity, confidence weighting, Audience Bridge Score, evaluated against Louvain and node2vec).

## Architecture and responsibilities

```
YouTube Data API v3          external source of public data
        ↓
Collection pipeline          (later step) validate → pseudonymize commenter ids → write
        ↓
Supabase PostgreSQL          shared, persistent CURRENT dataset for all four researchers
        ↓  export_snapshot_day + create_snapshot
Parquet snapshots            immutable, sealed HISTORICAL datasets (reproducible experiment inputs)
        ↓
DuckDB                       analytical SQL: joins, aggregation, feature preparation
        ↓
C1 / C2 / C3 / C4            research models and algorithms
```

| Layer | Responsibility | Not used for |
|---|---|---|
| **YouTube Data API v3** | Source of public channel, video and comment data | Storage |
| **Supabase PostgreSQL** | One online, shared, always-current dataset; collectors write here; current-state queries | Reproducible experiments (values change over time) |
| **Parquet snapshots** | Frozen, checksummed, per-day research datasets; archival; experiment inputs | Live shared writes |
| **DuckDB** | Fast local analysis of snapshots and Parquet (features, joins, graph preparation) | Shared persistent storage |

**Why Supabase:** all four researchers need the *same* dataset. Git doesn't hold data, and local files differ per laptop. A hosted PostgreSQL database gives one shared, persistent, current-state copy.

**Why Parquet remains:** experiments must be reproducible. A database row is overwritten when newer metrics arrive, whereas a sealed snapshot never changes, and its manifest records exactly what was used ([snapshots.md](snapshots.md)).

**Why DuckDB remains:** analytical work such as building the commenter–video–channel graph and computing features over many comments is much faster in DuckDB over columnar Parquet than through row-by-row database queries ([analytics.md](analytics.md)).

## Database schema (`research` schema)

The tables mirror the STEP 03 schemas (`shared/schemas/entities.py`); a test checks that the columns match.

| Table | Key | Notes |
|---|---|---|
| `channels` | `channel_id` | Latest observation per channel |
| `videos` | `video_id` | FK → `channels`; `tags text[]` |
| `comments` | `comment_id` | FK → `videos` and `channels`; `author_channel_id` must be a pseudonym (`anon_` + 64 hex), **enforced by a database CHECK** |
| `channel_stats_history` | (`channel_id`, `collected_at`) | Every observed subscriber, view and video count |
| `video_stats_history` | (`video_id`, `collected_at`) | Every observed view, like and comment count |
| `schema_migrations` | `version` | Applied migrations |

All current-state tables also have:
- `collected_at`: the latest observation
- `first_collected_at`: when the record was first seen
- `updated_at`: the last write to the row

`published_at` (YouTube's time) is kept separate from `collected_at` (our time). ID formats are checked, and counts must be ≥ 0. Missing metrics stay `NULL`, never 0.

**Indexes**, each justified by a planned query:
- `videos (channel_id, published_at DESC)`: a channel's videos.
- `videos (published_at)`: date ranges across all videos.
- `comments (video_id, published_at)`: a video's comments in time order.
- `comments (channel_id)`: commenter–channel edges.
- `comments (author_channel_id)` (partial, non-null): one commenter across channels, for audience bridges.
- `comments (published_at)`: date ranges.

Primary keys index the IDs.

## Upsert and duplicate strategy

The same rules as Parquet storage ([dataset_storage.md](dataset_storage.md)), using the same validation code:

| Situation | Result |
|---|---|
| New ID | Inserted |
| Same ID, **newer or equal** `collected_at`, values changed | Current row updated |
| Same ID, nothing changed | Left as is (`unchanged_or_older`) |
| Same ID, **older** `collected_at` (late data) | Current row kept; never overwritten by older data |
| Any channel or video observation | Also written to `*_stats_history`, so earlier metric values are **never lost** |
| Two different versions with the same ID and `collected_at` in one batch | `DuplicateRecordError`; nothing written |
| `insert_*` with an existing ID | `DuplicateKeyError` |
| Video or comment referencing a missing channel or video | `ReferentialIntegrityError`; the whole batch is rolled back |

**Order of writes:** channels, then videos, then comments, because foreign keys require the parent first. Each batch is atomic (a savepoint) and joins the caller's transaction; `database()` commits on success and rolls back on error.

## Privacy

- Commenter IDs are pseudonymized before writing (`shared/utils/privacy.py`), and the database **rejects** anything that isn't a pseudonym, so raw IDs can't enter even by mistake.
- No names, emails, private account data, demographics, watch history or subscription status are stored.
- A shared pseudonym across channels is an **observable interaction signal**, not proof of audience migration or subscription.
- **Access:** row-level security is enabled on every table with no policies, and the `research` schema isn't exposed through Supabase's REST API. The public `anon` key therefore can't read research data; only the server-side `SUPABASE_DB_URL` connection can.

## Setup

### 1. Create the project (once, by one team member)
1. [supabase.com](https://supabase.com) → **New project**: name `j26-ds-334`, region **Southeast Asia (Singapore)**, a strong database password saved in a password manager.
2. Add the other three members under **Organization → Team**.

### 2. Configure `.env` (every member)
Copy the placeholders from `.env.example` into `.env` and fill them in. **Never** put the real values in `.env.example`, code or chat.

| Variable | Where in Supabase | Secret? |
|---|---|---|
| `SUPABASE_URL` | Project Settings → Data API → Project URL | No |
| `SUPABASE_ANON_KEY` | Project Settings → API Keys → `anon` / publishable | Low risk, but keep in `.env` |
| `SUPABASE_DB_URL` | **Connect → Session pooler** connection string, with your password filled in | **Yes**: full database access |

Use the **Session pooler** string (port 5432). It works on IPv4 networks and supports this client. Supabase hosts automatically get `sslmode=require`.

### 3. Create or update the tables

Migrations: `0001_research_schema` (tables), `0002_channel_description_published` (schema 1.1 channel fields), `0003_video_duration` (schema 1.2 `videos.duration_seconds`), `0004_comment_replies` (schema 1.3 `comments.parent_comment_id`, `edited_at`). Run the command again after pulling new migrations.
```powershell
python -m shared.database.migrate status   # what is applied / pending
python -m shared.database.migrate          # apply pending migrations (safe to re-run)
```

## Usage

```python
from shared.database.connection import database
from shared.database import repository as repo
from shared.database.snapshot_export import export_snapshot_day

with database() as conn:                       # commits on success, rolls back on error
    repo.upsert_channels(conn, channels)       # Channel objects or dicts
    repo.upsert_videos(conn, videos)
    repo.upsert_comments(conn, comments)       # commenter ids pseudonymized automatically
    repo.list_videos(conn, "UC...")            # -> [Video, ...]
    repo.stats_history(conn, "videos", "VIDEO_ID")

# End of a collection day: database -> sealed Parquet snapshot -> DuckDB
with database() as conn:
    export_snapshot_day(conn, "2026-10-08", seal=True)
```

| Function | Purpose |
|---|---|
| `insert_channel/video/comment` | Insert one new record (error if it exists) |
| `upsert_channels/videos/comments` (aliases `update_*`) | Incremental batch write; returns `WriteSummary(inserted, updated, unchanged_or_older)` |
| `get_channel/video/comment` | One record or `None` |
| `list_channels`, `list_videos(channel_id)`, `list_comments(video_id= / channel_id=)` | Ordered lists |
| `stats_history(dataset, id)` | Metric history of a channel or video |
| `fetch_collected_on(dataset, day)` | Rows collected on a UTC day (used by the snapshot export) |

A snapshot day contains the rows whose latest observation was collected that day. Export it **at the end of each collection day**, before the next day's collection replaces those rows. Earlier metric values remain in `*_stats_history` regardless.

## Channel collector

`python -m shared.data_collection.channel_collector` collects the configured channels into `research.channels`.

**Configuration:** `config/research_channels.json` defines groups (`owned`, `competitor`; more can be added). Each group lists confirmed organizations (`config/organizations/<slug>.json`, from discovery) and/or individual `channel_ids`. A channel may be in only one group. The collector reads only this file; no IDs are in the code.

```powershell
python -m shared.data_collection.channel_collector --dry-run        # fetch + validate, store nothing
python -m shared.data_collection.channel_collector                  # all groups -> Supabase
python -m shared.data_collection.channel_collector --group owned
```

**What it does:**
1. Calls `channels.list` (part `snippet,statistics`) for up to 50 IDs per request, at **1 quota unit per 50 channels**. It never uses `search.list`.
2. Validates each channel with the `Channel` schema.
3. Upserts it into Supabase, committing after each batch. Each channel and batch is processed independently, so one failure never stops the others.

**What it stores:**
- Name, description, creation date (`published_at`).
- Subscriber, view and video counts. A hidden subscriber count is stored as `NULL`, not 0.
- `collected_at`, the time of the API response.
- Earlier metric values stay in `channel_stats_history`.

**Repeat runs:**
- A channel seen for the first time is **inserted**.
- On later runs it's **updated**, and no duplicate is ever created.
- Re-running is safe.

**Results:** the summary reports each channel as collected, inserted, updated, unchanged, failed or skipped. "Updated" is split into **values changed** (e.g. subscribers or views differ) and **refreshed only** (same values, newer `collected_at`). Failures carry a reason:
- `invalid_id`
- `not_found`
- `validation_error`
- `api_error`
- `storage_error`
- `quota_exceeded` and `auth_error`: these stop the run, and the remaining channels are reported as skipped.

Invalid records are never stored. The exit code is `0` when every channel succeeded, `1` when some failed, and `2` for configuration problems.

Channel data is only the foundation. It says nothing about audience movement, subscriptions, identity or causality.

## Video collector

`python -m shared.data_collection.video_collector` collects the videos of the configured channels into `research.videos`. It uses the same `config/research_channels.json` groups.

```powershell
python -m shared.data_collection.video_collector --dry-run            # fetch + validate, store nothing
python -m shared.data_collection.video_collector                      # 50 newest videos per channel
python -m shared.data_collection.video_collector --max-videos 10 --group owned
python -m shared.data_collection.video_collector --since 2026-09-01   # stop at older videos
```

**Run the channel collector first.** Videos are only collected for channels already in `research.channels`. Any other channel is reported as `channel_not_stored` and costs no quota, so no orphan videos are created.

**API strategy (never `search.list`):**

| Step | Call | Cost |
|---|---|---|
| Find each channel's uploads playlist | `channels.list` (`contentDetails`) | 1 unit per 50 channels |
| List video IDs, newest first | `playlistItems.list`, paginated | 1 unit per 50 videos |
| Fetch metadata and statistics | `videos.list` (`snippet,statistics,contentDetails`), batches of 50 | 1 unit per 50 videos |

For example, 60 channels × 50 videos costs about 2 + 60 + 60 = **~120 units**.

**Pagination:**
- Follows `nextPageToken` until the last page, `--max-videos`, or the first video older than `--since`.
- A repeated page token, or more than 200 pages, stops that channel with `pagination_error`, so it can never loop.
- A missing or empty uploads playlist means 0 videos.

**What it stores:**
- Title, description, tags, `published_at` (YouTube's time) and `duration_seconds`.
- View, like and comment counts. Hidden likes and disabled comments are stored as `NULL`, not 0.
- `collected_at` (our time).
- Earlier counts stay in `video_stats_history`.

**Repeat runs:**
- A new video is **inserted**; a known video is **updated**, split into values changed and refreshed only.
- No duplicates are created.

**Failures:**
- **Per channel:** `invalid_id`, `channel_not_stored`, `not_found`, `no_uploads_playlist`, `pagination_error`, `api_error`.
- **Per video:**
  - `unavailable` (private or deleted)
  - `validation_error` (not stored)
  - `channel_mismatch`
  - `api_error`
  - `storage_error`
- `quota_exceeded` and `auth_error` stop the run, and the remaining channels are skipped.

One channel's failure never affects another's results.

## Comment collector

`python -m shared.data_collection.comment_collector` collects comments of the **videos already stored** in `research.videos`. It never discovers videos itself.

```powershell
python -m shared.data_collection.comment_collector --dry-run          # fetch + validate, store nothing
python -m shared.data_collection.comment_collector                    # videos of all configured groups
python -m shared.data_collection.comment_collector --group owned --max-threads 50
python -m shared.data_collection.comment_collector --video VIDEO_ID   # selected videos (repeatable)
python -m shared.data_collection.comment_collector --new-only         # only videos without stored comments
python -m shared.data_collection.comment_collector --incremental      # stop at threads already stored
```

**Run order:** channel collector → video collector → comment collector.

**API strategy (never `search.list`):**

| Call | When | Cost |
|---|---|---|
| `commentThreads.list` (`snippet,replies`, `order=time`, plain text, 100 threads per page) | Every video, paginated up to `--max-threads` (default 100) | 1 unit per page |
| `comments.list` (`parentId`) | Only when a thread has more replies than the up to 5 that YouTube embeds | 1 unit per 100 replies |

**Quota savings:**
- Videos whose stored `comment_count` is 0 are skipped without any API call.
- `--no-extra-replies` keeps only the embedded replies.
- `--incremental` stops paging once it reaches threads that are already stored. New replies on old threads are then missed until a full run.

**Replies:** top-level comments have `parent_comment_id = NULL`, and replies point to their thread. Each comment is stored once, even if it appears in both the embedded replies and `comments.list`. Replies of an invalid parent aren't stored, so there are no orphan replies.

**Privacy:**
- Commenter channel IDs are turned into pseudonyms (`anon_` + HMAC-SHA256 with `COMMENTER_HASH_SALT`) **as soon as they're parsed**.
- The same commenter always gets the same pseudonym across videos, channels and runs, given the same salt. That's what makes cross-channel overlap detectable.
- Raw IDs, display names and profile images are never stored, logged or returned.
- Without a valid salt the collector stops **before any API call**.
- A pseudonym is an interaction signal only. It doesn't prove identity, subscription, audience migration, influence or causality.

**Repeat runs:**
- A new comment is **inserted**.
- A known comment is **updated**: changed text (`edited_at`) or like count counts as "values changed", otherwise "refreshed only". There are never duplicates.
- `published_at` is YouTube's posting time and is never replaced by `collected_at`.

**Expected vs unexpected:**
- **Expected, not errors:**
  - videos with **disabled comments** (`commentsDisabled`) are reported as "comments disabled"
  - deleted comments simply aren't returned by the API
- **Errors, per video:**
  - `video_unavailable` (404)
  - `api_error` (400, 403, 429, 5xx, network, malformed)
  - `pagination_error`
  - `replies_api_error` (the embedded replies are kept)
- **Errors, per comment:** `validation_error` (not stored), `video_mismatch`, `storage_error`.
- **Stops the run:** quota exhausted or an authentication failure.

## Tests

```powershell
python -m pytest tests/shared/test_database.py
```
- Configuration and connection tests need no database.
- Database tests start a **throwaway local PostgreSQL** (requires a local PostgreSQL installation for `initdb`/`pg_ctl`) and delete it afterwards. Set `TEST_DATABASE_URL` to use another disposable server, such as Docker.
- Tests **refuse to run against a Supabase host** and never use real credentials. Without PostgreSQL tools they're skipped with a message.
