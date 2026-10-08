"""YouTube comment collector: stored videos -> comment threads + replies -> pseudonymize -> Supabase.

    python -m shared.data_collection.comment_collector                        # videos of all configured groups
    python -m shared.data_collection.comment_collector --group owned
    python -m shared.data_collection.comment_collector --video VIDEO_ID       # selected videos (repeatable)
    python -m shared.data_collection.comment_collector --new-only             # videos without stored comments
    python -m shared.data_collection.comment_collector --incremental          # stop at already-stored threads
    python -m shared.data_collection.comment_collector --max-threads 100 --dry-run

Videos come from the database (the video collector's output); this collector
never discovers videos. API (never search.list):
  * commentThreads.list (snippet,replies; order=time; 100 threads/page)   1 unit per page
  * comments.list (parentId) only when a thread has more replies than     1 unit per page
    the up-to-5 that commentThreads embeds

Privacy: commenter channel ids are pseudonymized immediately when parsed
(shared.utils.privacy: HMAC with COMMENTER_HASH_SALT). Raw ids are never stored,
logged or returned. Display names and profile images are never read.
A pseudonym is an interaction signal only: it does not prove identity,
subscription, audience migration or causality.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from shared.data_collection import youtube_client as yc
from shared.schemas import Comment
from shared.utils import privacy

THREAD_PARTS = "snippet,replies"
DEFAULT_MAX_THREADS = 100          # top-level comments per video and run (1 API page)
MAX_PAGES = 200                    # hard stop against runaway pagination
FATAL_ERRORS = (yc.QuotaExceededError, yc.InvalidAPIKeyError, yc.UnauthorizedError, yc.MissingAPIKeyError)
DISABLED_REASONS = {"commentsDisabled"}


@dataclass(frozen=True)
class VideoRef:
    """A stored video to collect comments for (from research.videos)."""
    video_id: str
    channel_id: str
    comment_count: int | None = None        # YouTube's public count when the video was collected
    latest_stored_comment: datetime | None = None  # newest stored top-level comment (for --incremental)


@dataclass(frozen=True)
class CommentFailure:
    video_id: str
    reason: str
    message: str
    comment_id: str | None = None


Store = Callable[[list[Comment]], Any]  # -> repository.WriteSummary


@dataclass
class CommentCollectionResult:
    videos_requested: list[str]
    videos_processed: list[str] = field(default_factory=list)
    videos_skipped: list[str] = field(default_factory=list)            # no comments to fetch, or run stopped
    videos_with_comments_disabled: list[str] = field(default_factory=list)
    comments_discovered: int = 0
    comments_collected: list[str] = field(default_factory=list)        # validated
    comments_inserted: list[str] = field(default_factory=list)
    comments_updated: list[str] = field(default_factory=list)
    comments_changed: list[str] = field(default_factory=list)
    comments_refreshed: list[str] = field(default_factory=list)
    comments_unchanged: list[str] = field(default_factory=list)
    comments_skipped: int = 0                                           # malformed entries / beyond limits
    top_level_comments: int = 0
    replies: int = 0
    video_failures: list[CommentFailure] = field(default_factory=list)  # api / pagination problems
    comment_failures: list[CommentFailure] = field(default_factory=list)  # validation / storage problems
    quota_used: int = 0
    stored: bool = True
    started_at: str = ""
    finished_at: str = ""

    @property
    def validation_failures(self) -> list[CommentFailure]:
        return [f for f in self.comment_failures if f.reason in ("validation_error", "parent_invalid")]

    @property
    def api_failures(self) -> list[CommentFailure]:
        return [f for f in self.video_failures if f.reason not in ("storage_error",)]

    @property
    def database_failures(self) -> list[CommentFailure]:
        return [f for f in self.comment_failures + self.video_failures if f.reason == "storage_error"]

    @property
    def ok(self) -> bool:
        return not self.video_failures and not self.comment_failures

    def summary(self) -> str:
        lines = [
            f"Comment collection {self.started_at} -> {self.finished_at}"
            + ("" if self.stored else "  (dry run: nothing stored)"),
            f"  videos:   requested {len(self.videos_requested)} | processed {len(self.videos_processed)} | "
            f"comments disabled {len(self.videos_with_comments_disabled)} | skipped {len(self.videos_skipped)} | "
            f"failed {len({f.video_id for f in self.video_failures})}",
            f"  comments: discovered {self.comments_discovered} (top-level {self.top_level_comments}, "
            f"replies {self.replies}) | collected {len(self.comments_collected)} | "
            f"inserted {len(self.comments_inserted)} | updated {len(self.comments_updated)} "
            f"(values changed {len(self.comments_changed)}, refreshed only {len(self.comments_refreshed)}) | "
            f"failed {len(self.comment_failures)} | skipped {self.comments_skipped}",
            f"  quota used {self.quota_used}",
        ]
        for f in self.video_failures[:20]:
            lines.append(f"  VIDEO FAILED   {f.video_id}: {f.reason} - {f.message}")
        reasons: dict[str, int] = {}
        for f in self.comment_failures:
            reasons[f.reason] = reasons.get(f.reason, 0) + 1
        for reason, n in sorted(reasons.items()):
            lines.append(f"  COMMENTS FAILED {n} x {reason}")
        return "\n".join(lines)


class _Stop(Exception):
    pass


class _PaginationError(Exception):
    pass


def collect_comments(
    videos: Sequence[VideoRef],
    client: yc.YouTubeClient,
    store: Store | None,
    *,
    max_threads_per_video: int = DEFAULT_MAX_THREADS,
    fetch_all_replies: bool = True,
    incremental: bool = False,
    salt: bytes | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> CommentCollectionResult:
    """Collect comment threads (and replies) of the given stored videos. ``store=None`` is a dry run."""
    refs = list({v.video_id: v for v in videos}.values())
    if not refs:
        raise ValueError("no videos to collect comments for; run the video collector first")
    if isinstance(max_threads_per_video, bool) or not isinstance(max_threads_per_video, int) \
            or max_threads_per_video < 1:
        raise ValueError("max_threads_per_video must be a positive integer")
    key = salt if salt is not None else privacy.get_salt()  # fail closed before any API call

    result = CommentCollectionResult(videos_requested=[v.video_id for v in refs], stored=store is not None,
                                     started_at=_iso(clock()))
    quota_before = client.quota_used
    for n, ref in enumerate(refs):
        if not (yc.is_valid_id(ref.video_id) and yc.is_valid_id(ref.channel_id)):
            result.video_failures.append(CommentFailure(ref.video_id, "invalid_id", "invalid video or channel id"))
            continue
        if ref.comment_count == 0:
            result.videos_skipped.append(ref.video_id)  # nothing to fetch: no quota spent
            continue
        try:
            _collect_video(ref, client, store, result, key, max_threads_per_video, fetch_all_replies,
                           incremental, clock)
        except _Stop:
            result.videos_skipped += [r.video_id for r in refs[n + 1:]]
            break

    result.quota_used = client.quota_used - quota_before
    result.finished_at = _iso(clock())
    return result


def _collect_video(ref, client, store, result, key, limit, fetch_all_replies, incremental, clock) -> None:
    token: str | None = None
    seen_tokens: set[str] = set()
    threads_done = 0
    try:
        for _ in range(MAX_PAGES):
            page = client.comment_threads_list(
                part=THREAD_PARTS, video_id=ref.video_id, max_results=min(100, limit - threads_done),
                page_token=token, order="time", text_format="plainText")
            collected_at = clock()
            comments, reached_known = _parse_page(ref, page.items, client, result, key, collected_at,
                                                  fetch_all_replies, incremental)
            threads_done += sum(1 for c in comments if c.parent_comment_id is None)
            if comments:
                result.comments_collected += [c.comment_id for c in comments]
                if store is not None:
                    _store(ref, comments, store, result)
            token = page.next_page_token
            if not token or threads_done >= limit or reached_known:
                break
            if token in seen_tokens:
                raise _PaginationError("API returned the same page token twice; stopped to avoid a loop")
            seen_tokens.add(token)
        else:
            raise _PaginationError(f"more than {MAX_PAGES} pages; stopped")
    except FATAL_ERRORS as exc:
        reason = "quota_exceeded" if isinstance(exc, yc.QuotaExceededError) else "auth_error"
        result.video_failures.append(CommentFailure(ref.video_id, reason, _short(exc)))
        raise _Stop from None
    except yc.ForbiddenError as exc:
        if exc.reason in DISABLED_REASONS:
            result.videos_with_comments_disabled.append(ref.video_id)  # expected, not an error
            return
        result.video_failures.append(CommentFailure(ref.video_id, "api_error", _short(exc)))
        return
    except yc.NotFoundError as exc:
        result.video_failures.append(CommentFailure(ref.video_id, "video_unavailable", _short(exc)))
        return
    except _PaginationError as exc:
        result.video_failures.append(CommentFailure(ref.video_id, "pagination_error", str(exc)))
        return
    except yc.YouTubeAPIError as exc:
        result.video_failures.append(CommentFailure(ref.video_id, "api_error", _short(exc)))
        return
    result.videos_processed.append(ref.video_id)


def _parse_page(ref, items, client, result, key, collected_at, fetch_all_replies, incremental):
    """Threads of one page -> validated, pseudonymized comments (each comment once)."""
    out: dict[str, Comment] = {}
    reached_known = False
    for thread in items:
        top = ((thread or {}).get("snippet") or {}).get("topLevelComment") if isinstance(thread, dict) else None
        if not isinstance(top, dict) or not yc.is_valid_id(top.get("id")):
            result.comments_skipped += 1
            continue
        result.comments_discovered += 1
        result.top_level_comments += 1
        parent = _to_comment(top, ref, None, key, collected_at, result)
        if incremental and ref.latest_stored_comment and parent is not None \
                and parent.published_at <= ref.latest_stored_comment:
            reached_known = True  # order=time: the rest of the video's threads are already stored
        if parent is None:
            continue  # replies of an invalid parent are not stored (no orphan replies)
        out[parent.comment_id] = parent

        embedded = ((thread.get("replies") or {}).get("comments")) or []
        total = (thread.get("snippet") or {}).get("totalReplyCount") or 0
        replies = embedded
        if fetch_all_replies and isinstance(total, int) and total > len(embedded):
            replies = _all_replies(parent.comment_id, client, ref, result) or embedded
        for raw in replies:
            if not isinstance(raw, dict) or not yc.is_valid_id(raw.get("id")):
                result.comments_skipped += 1
                continue
            result.comments_discovered += 1
            result.replies += 1
            reply = _to_comment(raw, ref, parent.comment_id, key, collected_at, result)
            if reply is not None:
                out[reply.comment_id] = reply  # later copies replace earlier ones: no duplicates
    return list(out.values()), reached_known


def _all_replies(parent_id, client, ref, result) -> list[dict]:
    """All replies of a thread via comments.list (paginated). Fatal errors propagate."""
    replies: list[dict] = []
    token, seen = None, set()
    for _ in range(MAX_PAGES):
        try:
            page = client.comments_list(parent_id=parent_id, max_results=100, page_token=token,
                                        text_format="plainText")
        except FATAL_ERRORS:
            raise
        except yc.YouTubeAPIError as exc:
            result.video_failures.append(CommentFailure(ref.video_id, "replies_api_error", _short(exc), parent_id))
            return replies
        replies += page.items
        token = page.next_page_token
        if not token or token in seen:
            return replies
        seen.add(token)
    return replies


def to_comment_record(raw: dict[str, Any], ref: VideoRef, parent_id: str | None, key: bytes,
                      collected_at: datetime) -> dict[str, Any]:
    """Map a comment resource to the Comment schema. The commenter id is pseudonymized here;
    display names and profile images are deliberately not read."""
    s = raw.get("snippet") or {}
    author = (s.get("authorChannelId") or {}).get("value") if isinstance(s.get("authorChannelId"), dict) else None
    return {
        "comment_id": raw.get("id"),
        "video_id": ref.video_id,
        "channel_id": ref.channel_id,
        "author_channel_id": privacy.pseudonymize_id(author, key) if isinstance(author, str) and author.strip() else None,
        "comment_text": s.get("textDisplay") if s.get("textDisplay") is not None else s.get("textOriginal"),
        "published_at": s.get("publishedAt"),
        "edited_at": s.get("updatedAt"),
        "like_count": s.get("likeCount"),
        "parent_comment_id": parent_id,
        "collected_at": collected_at,
    }


def _to_comment(raw, ref, parent_id, key, collected_at, result) -> Comment | None:
    snippet = raw.get("snippet") or {}
    if snippet.get("videoId") not in (None, ref.video_id):
        result.comment_failures.append(CommentFailure(ref.video_id, "video_mismatch",
                                                      "comment belongs to another video", raw.get("id")))
        return None
    try:
        return Comment.model_validate(to_comment_record(raw, ref, parent_id, key, collected_at))
    except ValidationError as exc:
        fields = sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()})
        result.comment_failures.append(CommentFailure(ref.video_id, "validation_error",
                                                      f"invalid field(s): {', '.join(fields)}", raw.get("id")))
        return None


def _store(ref, comments, store, result) -> None:
    try:
        summary = store(comments)
    except Exception as exc:
        result.comment_failures += [CommentFailure(ref.video_id, "storage_error", _short(exc), c.comment_id)
                                    for c in comments]
        failed = {c.comment_id for c in comments}
        result.comments_collected = [c for c in result.comments_collected if c not in failed]
        return
    if summary is None:
        return
    result.comments_inserted += list(summary.inserted_ids)
    result.comments_updated += list(summary.updated_ids)
    result.comments_changed += list(summary.changed_ids)
    result.comments_refreshed += list(summary.refreshed_ids)
    done = set(summary.inserted_ids) | set(summary.updated_ids)
    result.comments_unchanged += [c.comment_id for c in comments if c.comment_id not in done]


# --- Supabase adapters ----------------------------------------------------------------

def supabase_store(conn) -> Store:
    """Write comments to Supabase; commits after each page."""
    from shared.database import repository

    def store(comments: list[Comment]):
        try:
            summary = repository.upsert_comments(conn, comments)
            conn.commit()
            return summary
        except Exception:
            conn.rollback()
            raise

    return store


def stored_videos(conn, *, channel_ids: Sequence[str] | None = None, video_ids: Sequence[str] | None = None,
                  new_only: bool = False) -> list[VideoRef]:
    """Videos to process, from research.videos (newest first), with their newest stored comment."""
    where, params = [], []
    if channel_ids is not None:
        where.append("v.channel_id = ANY(%s)")
        params.append(list(channel_ids))
    if video_ids is not None:
        where.append("v.video_id = ANY(%s)")
        params.append(list(video_ids))
    sql = """
        SELECT v.video_id, v.channel_id, v.comment_count,
               (SELECT max(c.published_at) FROM research.comments c
                 WHERE c.video_id = v.video_id AND c.parent_comment_id IS NULL) AS latest
        FROM research.videos v
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY v.published_at DESC, v.video_id"
    rows = conn.execute(sql, params).fetchall()
    conn.commit()
    refs = [VideoRef(r[0], r[1], r[2], r[3]) for r in rows]
    return [r for r in refs if r.latest_stored_comment is None] if new_only else refs


# --- helpers ----------------------------------------------------------------------

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

    parser = argparse.ArgumentParser(prog="comment_collector", description="Collect comments of stored videos.")
    parser.add_argument("--group", action="append", help="configured channel group (repeatable)")
    parser.add_argument("--video", action="append", help="only this stored video id (repeatable)")
    parser.add_argument("--new-only", action="store_true", help="only videos without stored comments")
    parser.add_argument("--incremental", action="store_true", help="stop at threads already stored")
    parser.add_argument("--max-threads", type=int, default=DEFAULT_MAX_THREADS,
                        help=f"top-level comments per video (default {DEFAULT_MAX_THREADS})")
    parser.add_argument("--no-extra-replies", action="store_true",
                        help="keep only the replies embedded in threads (saves quota)")
    parser.add_argument("--dry-run", action="store_true", help="fetch and validate only; store nothing")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        privacy.get_salt()  # fail before any API call if the privacy secret is missing
        channel_ids = [c.channel_id for c in load_channels(args.group)]
        client = yc.YouTubeClient()
        with connect() as conn:
            refs = stored_videos(conn, channel_ids=channel_ids, video_ids=args.video, new_only=args.new_only)
            if not refs:
                print("No eligible stored videos (run the video collector first, or adjust the filters).")
                return 0
            print(f"Collecting comments for {len(refs)} stored video(s), up to {args.max_threads} thread(s) each")
            result = collect_comments(
                refs, client, None if args.dry_run else supabase_store(conn),
                max_threads_per_video=args.max_threads, fetch_all_replies=not args.no_extra_replies,
                incremental=args.incremental)
    except (ChannelConfigError, yc.MissingAPIKeyError, privacy.PrivacyConfigError, DatabaseConfigError,
            DatabaseConnectionError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    print(result.summary())
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
