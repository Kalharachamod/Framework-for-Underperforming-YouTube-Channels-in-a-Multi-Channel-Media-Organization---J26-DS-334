"""Manual YouTube comment collection for Component 2."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from shared.data_collection.config import ChannelConfig
from shared.data_collection.youtube_client import YouTubeApiError


MAX_PLAYLIST_PAGE_SIZE = 50
MAX_COMMENT_PAGE_SIZE = 100


@dataclass
class CollectionStats:
    channels_seen: int = 0
    videos_seen: int = 0
    videos_skipped: int = 0
    comments_written: int = 0
    duplicates_skipped: int = 0
    replies_written: int = 0
    disabled_or_unavailable_videos: int = 0
    api_errors: int = 0
    quota_exhausted: bool = False
    dry_run: bool = False
    api_requests: int = 0
    started_at: str = field(default_factory=lambda: utc_now_iso())
    finished_at: str | None = None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def load_existing_comment_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    seen: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                comment_id = json.loads(line).get("comment_id")
            except json.JSONDecodeError:
                continue
            if comment_id:
                seen.add(comment_id)
    return seen


def append_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


class CommentCollector:
    def __init__(
        self,
        client: Any,
        output_dir: str | Path = "data/raw/component_2/comments",
        collect_replies: bool = False,
        dry_run: bool = False,
    ) -> None:
        self.client = client
        self.output_dir = Path(output_dir)
        self.collect_replies = collect_replies
        self.dry_run = dry_run

    def collect(
        self,
        channels: list[ChannelConfig],
        run_id: str,
        max_videos: int | None = None,
        comments_per_video: int | None = None,
        resume: bool = False,
    ) -> CollectionStats:
        run_dir = self.output_dir / run_id
        comments_path = run_dir / "comments.jsonl"
        checkpoint_path = run_dir / "checkpoint.json"
        stats_path = run_dir / "run_stats.json"

        checkpoint = load_json(
            checkpoint_path,
            {"processed_video_ids": [], "channel_upload_playlist_ids": {}},
        )
        processed_video_ids = set(checkpoint.get("processed_video_ids", [])) if resume else set()
        seen_comment_ids = load_existing_comment_ids(comments_path) if resume else set()
        stats = CollectionStats(dry_run=self.dry_run)

        for channel in channels:
            stats.channels_seen += 1
            playlist_id = self._get_uploads_playlist_id(channel, checkpoint)
            video_limit = min(
                max_videos if max_videos is not None else channel.max_videos_initial,
                channel.max_videos_initial,
            )
            per_video_limit = min(
                comments_per_video
                if comments_per_video is not None
                else channel.max_comments_per_video,
                channel.max_comments_per_video,
            )

            for video_id in self._iter_upload_video_ids(playlist_id, video_limit):
                if video_id in processed_video_ids:
                    stats.videos_skipped += 1
                    continue

                stats.videos_seen += 1
                if self.dry_run:
                    processed_video_ids.add(video_id)
                    self._save_checkpoint(checkpoint_path, checkpoint, processed_video_ids)
                    continue

                try:
                    written = self._collect_video_comments(
                        channel=channel,
                        video_id=video_id,
                        limit=per_video_limit,
                        comments_path=comments_path,
                        seen_comment_ids=seen_comment_ids,
                    )
                    stats.comments_written += written["comments"]
                    stats.replies_written += written["replies"]
                except YouTubeApiError as exc:
                    stats.api_errors += 1
                    if exc.quota_exhausted:
                        stats.quota_exhausted = True
                        break
                    if exc.reason in {
                        "commentsDisabled",
                        "videoNotFound",
                        "forbidden",
                        "processingFailure",
                    }:
                        stats.disabled_or_unavailable_videos += 1
                    else:
                        raise
                finally:
                    processed_video_ids.add(video_id)
                    self._save_checkpoint(checkpoint_path, checkpoint, processed_video_ids)

            if stats.quota_exhausted:
                break

        stats.duplicates_skipped = len(seen_comment_ids) - stats.comments_written
        stats.api_requests = getattr(self.client, "request_count", 0)
        stats.finished_at = utc_now_iso()
        write_json(stats_path, asdict(stats))
        return stats

    def _get_uploads_playlist_id(
        self, channel: ChannelConfig, checkpoint: dict[str, Any]
    ) -> str:
        cached = checkpoint.get("channel_upload_playlist_ids", {}).get(channel.channel_id)
        if cached:
            return cached

        response = self.client.channels_list(
            part="contentDetails", id=channel.channel_id, maxResults=1
        )
        items = response.get("items", [])
        if not items:
            raise ValueError(f"No YouTube channel found for {channel.channel_id}")
        playlist_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
        checkpoint.setdefault("channel_upload_playlist_ids", {})[
            channel.channel_id
        ] = playlist_id
        return playlist_id

    def _iter_upload_video_ids(self, playlist_id: str, limit: int) -> Iterable[str]:
        page_token = None
        yielded = 0
        while yielded < limit:
            response = self.client.playlist_items_list(
                part="contentDetails",
                playlistId=playlist_id,
                maxResults=min(MAX_PLAYLIST_PAGE_SIZE, limit - yielded),
                pageToken=page_token,
            )
            for item in response.get("items", []):
                video_id = item.get("contentDetails", {}).get("videoId")
                if video_id:
                    yielded += 1
                    yield video_id
                    if yielded >= limit:
                        break
            page_token = response.get("nextPageToken")
            if not page_token:
                break

    def _collect_video_comments(
        self,
        channel: ChannelConfig,
        video_id: str,
        limit: int,
        comments_path: Path,
        seen_comment_ids: set[str],
    ) -> dict[str, int]:
        page_token = None
        comment_count = 0
        reply_count = 0
        while comment_count < limit:
            response = self.client.comment_threads_list(
                part="snippet,replies",
                videoId=video_id,
                maxResults=min(MAX_COMMENT_PAGE_SIZE, limit - comment_count),
                pageToken=page_token,
                textFormat="plainText",
                order="time",
            )
            records: list[dict[str, Any]] = []
            for item in response.get("items", []):
                top = item["snippet"]["topLevelComment"]
                comment_record = self._comment_record(
                    comment=top,
                    video_id=video_id,
                    channel=channel,
                    parent_id=None,
                    is_reply=False,
                    total_reply_count=item["snippet"].get("totalReplyCount", 0),
                )
                if comment_record["comment_id"] in seen_comment_ids:
                    continue
                seen_comment_ids.add(comment_record["comment_id"])
                records.append(comment_record)
                comment_count += 1

                if self.collect_replies:
                    replies = self._reply_records(
                        parent_id=comment_record["comment_id"],
                        video_id=video_id,
                        channel=channel,
                    )
                    for reply in replies:
                        if reply["comment_id"] not in seen_comment_ids:
                            seen_comment_ids.add(reply["comment_id"])
                            records.append(reply)
                            reply_count += 1

                if comment_count >= limit:
                    break

            append_jsonl(comments_path, records)
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return {"comments": comment_count, "replies": reply_count}

    def _reply_records(
        self, parent_id: str, video_id: str, channel: ChannelConfig
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        page_token = None
        while True:
            response = self.client.comments_list(
                part="snippet",
                parentId=parent_id,
                maxResults=MAX_COMMENT_PAGE_SIZE,
                pageToken=page_token,
                textFormat="plainText",
            )
            for item in response.get("items", []):
                records.append(
                    self._comment_record(
                        comment=item,
                        video_id=video_id,
                        channel=channel,
                        parent_id=parent_id,
                        is_reply=True,
                        total_reply_count=0,
                    )
                )
            page_token = response.get("nextPageToken")
            if not page_token:
                return records

    @staticmethod
    def _comment_record(
        comment: dict[str, Any],
        video_id: str,
        channel: ChannelConfig,
        parent_id: str | None,
        is_reply: bool,
        total_reply_count: int,
    ) -> dict[str, Any]:
        snippet = comment["snippet"]
        return {
            "comment_id": comment["id"],
            "video_id": video_id,
            "channel_id": channel.channel_id,
            "channel_name": channel.channel_name,
            "text": snippet.get("textDisplay") or snippet.get("textOriginal") or "",
            "published_at": snippet.get("publishedAt"),
            "updated_at": snippet.get("updatedAt"),
            "like_count": snippet.get("likeCount", 0),
            "parent_id": parent_id,
            "is_reply": is_reply,
            "total_reply_count": total_reply_count,
            "collected_at": utc_now_iso(),
        }

    @staticmethod
    def _save_checkpoint(
        checkpoint_path: Path,
        checkpoint: dict[str, Any],
        processed_video_ids: set[str],
    ) -> None:
        checkpoint["processed_video_ids"] = sorted(processed_video_ids)
        checkpoint["updated_at"] = utc_now_iso()
        write_json(checkpoint_path, checkpoint)
