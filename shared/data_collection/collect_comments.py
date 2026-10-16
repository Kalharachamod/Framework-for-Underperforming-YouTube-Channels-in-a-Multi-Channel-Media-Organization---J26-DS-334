"""CLI for manual Component 2 YouTube comment collection."""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

from shared.data_collection.comment_collector import CommentCollector
from shared.data_collection.config import filter_comment_channels, load_channel_registry
from shared.data_collection.env import load_dotenv
from shared.data_collection.youtube_client import YouTubeClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manually collect public YouTube comments for Component 2."
    )
    parser.add_argument(
        "--channel",
        default="all",
        help="Channel ID/name to collect, or 'all' for all active configured channels.",
    )
    parser.add_argument(
        "--registry",
        default="config/channel_registry.csv",
        help="Path to the channel registry CSV.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/raw/component_2/comments",
        help="Directory where run folders and JSONL output are written.",
    )
    parser.add_argument("--run-id", help="Stable run ID. Defaults to a UTC timestamp.")
    parser.add_argument("--max-videos", type=int, help="Limit videos per channel.")
    parser.add_argument(
        "--comments-per-video", type=int, help="Limit top-level comments per video."
    )
    parser.add_argument(
        "--include-replies", action="store_true", help="Also collect comment replies."
    )
    parser.add_argument(
        "--resume", action="store_true", help="Resume using an existing run directory."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve channels/videos and write checkpoint/statistics without comments.",
    )
    return parser


def default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)

    channels = filter_comment_channels(
        load_channel_registry(args.registry), selector=args.channel
    )
    run_id = args.run_id or default_run_id()
    api_key = os.environ.get("YOUTUBE_API_KEY", "")

    if not api_key:
        raise SystemExit(
            "YOUTUBE_API_KEY is not configured. Add it to .env or export it in the shell."
        )

    collector = CommentCollector(
        client=YouTubeClient(api_key=api_key),
        output_dir=Path(args.output_dir),
        collect_replies=args.include_replies,
        dry_run=args.dry_run,
    )
    stats = collector.collect(
        channels=channels,
        run_id=run_id,
        max_videos=args.max_videos,
        comments_per_video=args.comments_per_video,
        resume=args.resume,
    )

    print(f"Run ID: {run_id}")
    print(f"Channels processed: {stats.channels_seen}")
    print(f"Videos seen: {stats.videos_seen}")
    print(f"Comments written: {stats.comments_written}")
    print(f"Replies written: {stats.replies_written}")
    print(f"API requests: {stats.api_requests}")
    print(f"Output: {Path(args.output_dir) / run_id}")
    if stats.quota_exhausted:
        print("Stopped because the YouTube API quota appears exhausted.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
