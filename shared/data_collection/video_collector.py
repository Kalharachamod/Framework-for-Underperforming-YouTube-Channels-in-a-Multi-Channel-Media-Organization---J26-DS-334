"""YouTube video collector: configured channels -> uploads playlists -> videos -> Supabase.

    python -m shared.data_collection.video_collector                      # all groups, 50 newest per channel
    python -m shared.data_collection.video_collector --max-videos 10
    python -m shared.data_collection.video_collector --since 2026-09-01   # only videos published since
    python -m shared.data_collection.video_collector --group owned --dry-run

Quota-efficient strategy (never search.list):
  1. channels.list part=contentDetails        -> each channel's uploads playlist   (1 unit / 50 channels)
  2. playlistItems.list, paginated            -> video ids, newest first          (1 unit / 50 videos)
  3. videos.list, batches of 50               -> metadata + statistics            (1 unit / 50 videos)

Channels must already be stored by the channel collector: videos of unknown
channels are not collected (no orphan videos, no wasted quota).
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from pydantic import ValidationError

from shared.data_collection import youtube_client as yc
from shared.schemas import Video

BATCH_SIZE = 50
VIDEO_PARTS = "snippet,statistics,contentDetails"
DEFAULT_MAX_VIDEOS = 50
MAX_PAGES_PER_CHANNEL = 200  # hard stop against runaway pagination (10,000 videos)
FATAL_ERRORS = (yc.QuotaExceededError, yc.InvalidAPIKeyError, yc.UnauthorizedError, yc.MissingAPIKeyError)

Store = Callable[[list[Video]], Any]                  # -> repository.WriteSummary
KnownChannels = Callable[[list[str]], set[str]]       # which channel ids exist in the database
_DURATION = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")


@dataclass(frozen=True)
class CollectionFailure:
    channel_id: str
    reason: str
    message: str
    video_id: str | None = None


@dataclass
class VideoCollectionResult:
    channels_requested: list[str]
    channels_processed: list[str] = field(default_factory=list)
    videos_discovered: int = 0
    videos_collected: list[str] = field(default_factory=list)     # fetched + validated
    videos_inserted: list[str] = field(default_factory=list)
    videos_updated: list[str] = field(default_factory=list)       # = changed + refreshed
    videos_changed: list[str] = field(default_factory=list)
    videos_refreshed: list[str] = field(default_factory=list)
    videos_unchanged: list[str] = field(default_factory=list)
    channel_failures: list[CollectionFailure] = field(default_factory=list)
    video_failures: list[CollectionFailure] = field(default_factory=list)
    channels_skipped: list[str] = field(default_factory=list)     # not attempted (run stopped early)
    quota_used: int = 0
    stored: bool = True
    started_at: str = ""
    finished_at: str = ""

    @property
    def errors(self) -> list[CollectionFailure]:
        return self.channel_failures + self.video_failures

    @property
    def ok(self) -> bool:
        return not self.errors and not self.channels_skipped

    def summary(self) -> str:
        lines = [
            f"Video collection {self.started_at} -> {self.finished_at}"
            + ("" if self.stored else "  (dry run: nothing stored)"),
            f"  channels: requested {len(self.channels_requested)} | processed {len(self.channels_processed)} | "
            f"failed {len(self.channel_failures)} | skipped {len(self.channels_skipped)}",
            f"  videos:   discovered {self.videos_discovered} | collected {len(self.videos_collected)} | "
            f"inserted {len(self.videos_inserted)} | updated {len(self.videos_updated)} "
            f"(values changed {len(self.videos_changed)}, refreshed only {len(self.videos_refreshed)}) | "
            f"unchanged {len(self.videos_unchanged)} | failed {len(self.video_failures)}",
            f"  quota used {self.quota_used}",
        ]
        lines += [f"  CHANNEL FAILED {f.channel_id}: {f.reason} - {f.message}" for f in self.channel_failures]
        shown = self.video_failures[:20]
        lines += [f"  VIDEO FAILED   {f.video_id} ({f.channel_id}): {f.reason} - {f.message}" for f in shown]
        if len(self.video_failures) > len(shown):
            lines.append(f"  ... and {len(self.video_failures) - len(shown)} more video failures")
        if self.channels_skipped:
            lines.append(f"  SKIPPED {len(self.channels_skipped)} channel(s) after a fatal error")
        return "\n".join(lines)


class _Stop(Exception):
    """A fatal API error: stop the whole run."""


def collect_videos(
    channel_ids: Sequence[str],
    client: yc.YouTubeClient,
    store: Store | None,
    *,
    known_channels: KnownChannels | None = None,
    max_videos_per_channel: int = DEFAULT_MAX_VIDEOS,
    published_since: date | datetime | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> VideoCollectionResult:
    """Collect the newest videos of each channel. ``store=None`` is a dry run.

    ``known_channels`` returns the channel ids present in the database; channels
    not present are reported (``channel_not_stored``) and not collected.
    """
    ids = list(dict.fromkeys(c.strip() for c in channel_ids if isinstance(c, str)))
    if not ids:
        raise ValueError("no channel ids to collect; check config/research_channels.json")
    if isinstance(max_videos_per_channel, bool) or not isinstance(max_videos_per_channel, int) \
            or max_videos_per_channel < 1:
        raise ValueError("max_videos_per_channel must be a positive integer")
    since = _since(published_since)

    result = VideoCollectionResult(channels_requested=ids, stored=store is not None, started_at=_iso(clock()))
    quota_before = client.quota_used
    todo = []
    for cid in ids:
        if not yc.is_valid_id(cid):
            result.channel_failures.append(CollectionFailure(cid, "invalid_id", "not a valid YouTube channel id"))
        else:
            todo.append(cid)

    if todo and known_channels is not None:
        try:
            known = known_channels(todo)
        except Exception as exc:  # database unavailable: nothing can be stored safely
            result.channel_failures += [CollectionFailure(c, "storage_error", _short(exc)) for c in todo]
            todo = []
        else:
            for cid in [c for c in todo if c not in known]:
                result.channel_failures.append(CollectionFailure(
                    cid, "channel_not_stored", "channel is not in the database; run the channel collector first"))
            todo = [c for c in todo if c in known]

    try:
        uploads = _uploads_playlists(todo, client, result)
        for n, cid in enumerate(todo):
            if cid not in uploads:
                continue
            try:
                _collect_channel(cid, uploads[cid], client, store, result, max_videos_per_channel, since, clock)
            except _Stop:
                result.channels_skipped += [c for c in todo[n + 1:] if c in uploads]
                break
    except _Stop:
        pass

    result.quota_used = client.quota_used - quota_before
    result.finished_at = _iso(clock())
    return result


# --- steps ----------------------------------------------------------------------------

def _uploads_playlists(channel_ids: list[str], client, result) -> dict[str, str]:
    """channel id -> uploads playlist id, via channels.list (contentDetails)."""
    found: dict[str, str] = {}
    for start in range(0, len(channel_ids), BATCH_SIZE):
        batch = channel_ids[start:start + BATCH_SIZE]
        try:
            items = client.channels_list(part="contentDetails", id=batch).items
        except FATAL_ERRORS as exc:
            _fatal(batch, exc, result)
            result.channels_skipped += channel_ids[start + BATCH_SIZE:]
            raise _Stop from None
        except yc.YouTubeAPIError as exc:
            result.channel_failures += [CollectionFailure(c, "api_error", _short(exc)) for c in batch]
            continue
        by_id = {i.get("id"): i for i in items if isinstance(i, dict)}
        for cid in batch:
            playlist = (((by_id.get(cid) or {}).get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads")
            if cid not in by_id:
                result.channel_failures.append(CollectionFailure(cid, "not_found", "channel not returned by the API"))
            elif not playlist or not yc.is_valid_id(playlist):
                result.channel_failures.append(CollectionFailure(cid, "no_uploads_playlist",
                                                                 "API returned no uploads playlist for this channel"))
            else:
                found[cid] = playlist
    return found


def _collect_channel(cid, playlist, client, store, result, limit, since, clock) -> None:
    try:
        video_ids = _list_uploads(cid, playlist, client, limit, since)
    except FATAL_ERRORS as exc:
        _fatal([cid], exc, result)
        raise _Stop from None
    except _PaginationError as exc:
        result.channel_failures.append(CollectionFailure(cid, "pagination_error", str(exc)))
        return
    except yc.YouTubeAPIError as exc:
        result.channel_failures.append(CollectionFailure(cid, "api_error", _short(exc)))
        return

    result.videos_discovered += len(video_ids)
    for start in range(0, len(video_ids), BATCH_SIZE):
        batch = video_ids[start:start + BATCH_SIZE]
        try:
            items = client.videos_list(part=VIDEO_PARTS, id=batch).items
        except FATAL_ERRORS as exc:
            _fatal([cid], exc, result)
            raise _Stop from None
        except yc.YouTubeAPIError as exc:
            result.video_failures += [CollectionFailure(cid, "api_error", _short(exc), v) for v in batch]
            continue
        videos = _parse(cid, batch, items, clock(), result)
        result.videos_collected += [v.video_id for v in videos]
        if videos and store is not None:
            _store(cid, videos, store, result)
    result.channels_processed.append(cid)


class _PaginationError(Exception):
    pass


def _list_uploads(cid, playlist, client, limit, since) -> list[str]:
    """Video ids from the uploads playlist (newest first), up to ``limit`` / back to ``since``."""
    ids: list[str] = []
    token: str | None = None
    seen_tokens: set[str] = set()
    for _ in range(MAX_PAGES_PER_CHANNEL):
        try:
            page = client.playlist_items_list(playlist_id=playlist, max_results=min(50, limit - len(ids)),
                                              page_token=token)
        except yc.NotFoundError:
            return ids  # a channel without uploads has no (or an empty) uploads playlist
        reached_since = False
        for item in page.items:
            details = item.get("contentDetails") if isinstance(item, dict) else None
            vid = (details or {}).get("videoId")
            if not yc.is_valid_id(vid):
                continue  # skip malformed entries; counted as not discovered
            published = _parse_dt((details or {}).get("videoPublishedAt"))
            if since and published and published < since:
                reached_since = True
                continue
            if vid not in ids:
                ids.append(vid)
            if len(ids) >= limit:
                return ids
        token = page.next_page_token
        if not token or reached_since:
            return ids
        if token in seen_tokens:
            raise _PaginationError("API returned the same page token twice; stopped to avoid a loop")
        seen_tokens.add(token)
    raise _PaginationError(f"more than {MAX_PAGES_PER_CHANNEL} pages; stopped")


def _parse(cid, batch, items, collected_at, result) -> list[Video]:
    by_id = {i.get("id"): i for i in items if isinstance(i, dict)}
    videos = []
    for vid in batch:
        item = by_id.get(vid)
        if item is None:
            result.video_failures.append(CollectionFailure(
                cid, "unavailable", "no metadata returned (private, deleted or not yet processed)", vid))
            continue
        record = to_video_record(item, collected_at)
        if record["channel_id"] != cid:
            result.video_failures.append(CollectionFailure(
                cid, "channel_mismatch", "video belongs to a different channel than its uploads playlist", vid))
            continue
        try:
            videos.append(Video.model_validate(record))
        except ValidationError as exc:
            fields = sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()})
            result.video_failures.append(CollectionFailure(
                cid, "validation_error", f"invalid field(s): {', '.join(fields)}", vid))
    return videos


def to_video_record(item: dict[str, Any], collected_at: datetime) -> dict[str, Any]:
    """Map a videos.list resource to the Video schema fields (public metadata only)."""
    snippet = item.get("snippet") or {}
    stats = item.get("statistics") or {}
    details = item.get("contentDetails") or {}
    return {
        "video_id": item.get("id"),
        "channel_id": snippet.get("channelId"),
        "title": snippet.get("title"),
        "description": snippet.get("description"),
        "published_at": snippet.get("publishedAt"),
        "tags": snippet.get("tags") or [],
        "view_count": stats.get("viewCount"),
        "like_count": stats.get("likeCount"),        # absent when likes are hidden
        "comment_count": stats.get("commentCount"),  # absent when comments are disabled
        "duration_seconds": parse_duration(details.get("duration")),
        "collected_at": collected_at,
    }


def parse_duration(value: Any) -> int | None:
    """ISO 8601 duration (e.g. PT1H2M3S, P1DT2H) -> seconds; None if missing or malformed."""
    if not isinstance(value, str):
        return None
    m = _DURATION.fullmatch(value)
    if not m or value in ("P", "PT"):
        return None
    d, h, mi, s = (int(x) if x else 0 for x in m.groups())
    return ((d * 24 + h) * 60 + mi) * 60 + s


def _store(cid, videos, store, result) -> None:
    try:
        summary = store(videos)
    except Exception as exc:
        result.video_failures += [CollectionFailure(cid, "storage_error", _short(exc), v.video_id) for v in videos]
        failed = {v.video_id for v in videos}
        result.videos_collected = [v for v in result.videos_collected if v not in failed]
        return
    if summary is None:
        return
    result.videos_inserted += list(summary.inserted_ids)
    result.videos_updated += list(summary.updated_ids)
    result.videos_changed += list(summary.changed_ids)
    result.videos_refreshed += list(summary.refreshed_ids)
    done = set(summary.inserted_ids) | set(summary.updated_ids)
    result.videos_unchanged += [v.video_id for v in videos if v.video_id not in done]


def _fatal(channel_ids, exc, result) -> None:
    reason = "quota_exceeded" if isinstance(exc, yc.QuotaExceededError) else "auth_error"
    result.channel_failures += [CollectionFailure(c, reason, _short(exc)) for c in channel_ids]


# --- Supabase adapters ---------------------------------------------------------------

def supabase_store(conn) -> Store:
    """Write videos to Supabase; commits after each batch."""
    from shared.database import repository

    def store(videos: list[Video]):
        try:
            summary = repository.upsert_videos(conn, videos)
            conn.commit()
            return summary
        except Exception:
            conn.rollback()
            raise

    return store


def supabase_known_channels(conn) -> KnownChannels:
    def known(channel_ids: list[str]) -> set[str]:
        rows = conn.execute("SELECT channel_id FROM research.channels WHERE channel_id = ANY(%s)",
                            [list(channel_ids)]).fetchall()
        conn.commit()
        return {r[0] for r in rows}

    return known


# --- helpers -------------------------------------------------------------------------

def _since(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("published_since datetime must include a time zone")
        return value.astimezone(timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    raise ValueError("published_since must be a date or datetime")


def _parse_dt(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")) if value else None
    except ValueError:
        return None


def _short(exc: BaseException) -> str:
    text = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
    return text[:300]


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# --- command line ---------------------------------------------------------------------

def main(argv: Iterable[str] | None = None) -> int:
    import argparse

    from shared.data_collection.channel_config import ChannelConfigError, load_channels
    from shared.database.connection import DatabaseConfigError, DatabaseConnectionError, connect

    parser = argparse.ArgumentParser(prog="video_collector", description="Collect videos of configured channels.")
    parser.add_argument("--group", action="append", help="configured group to collect (repeatable)")
    parser.add_argument("--max-videos", type=int, default=DEFAULT_MAX_VIDEOS,
                        help=f"newest videos per channel (default {DEFAULT_MAX_VIDEOS})")
    parser.add_argument("--since", type=date.fromisoformat, help="only videos published on/after YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="fetch and validate only; store nothing")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        configured = load_channels(args.group)
        client = yc.YouTubeClient()
        ids = [c.channel_id for c in configured]
        print(f"Collecting up to {args.max_videos} video(s) per channel for {len(ids)} channel(s)"
              + (f" published since {args.since}" if args.since else ""))
        with connect() as conn:
            result = collect_videos(
                ids, client, None if args.dry_run else supabase_store(conn),
                known_channels=supabase_known_channels(conn),
                max_videos_per_channel=args.max_videos, published_since=args.since)
    except (ChannelConfigError, yc.MissingAPIKeyError, DatabaseConfigError, DatabaseConnectionError,
            ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    print(result.summary())
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
