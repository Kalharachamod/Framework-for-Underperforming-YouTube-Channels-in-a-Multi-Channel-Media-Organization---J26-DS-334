"""Configuration loading for shared YouTube collection jobs."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ChannelConfig:
    channel_name: str
    channel_id: str
    is_active: bool
    collect_comments: bool
    max_videos_initial: int
    max_comments_per_video: int
    snapshot_recent_days: int


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


def load_channel_registry(path: str | Path) -> list[ChannelConfig]:
    registry_path = Path(path)
    with registry_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        channels = [
            ChannelConfig(
                channel_name=row["channel_name"].strip(),
                channel_id=row["channel_id"].strip(),
                is_active=parse_bool(row["is_active"]),
                collect_comments=parse_bool(row["collect_comments"]),
                max_videos_initial=int(row["max_videos_initial"]),
                max_comments_per_video=int(row["max_comments_per_video"]),
                snapshot_recent_days=int(row["snapshot_recent_days"]),
            )
            for row in reader
        ]

    if not channels:
        raise ValueError(f"No channels found in registry: {registry_path}")
    return channels


def filter_comment_channels(
    channels: list[ChannelConfig], selector: str = "all"
) -> list[ChannelConfig]:
    enabled = [c for c in channels if c.is_active and c.collect_comments]
    if selector == "all":
        return enabled

    selector_key = selector.strip().lower()
    selected = [
        c
        for c in enabled
        if c.channel_id.lower() == selector_key
        or c.channel_name.strip().lower() == selector_key
    ]
    if not selected:
        raise ValueError(f"No active comment-enabled channel matches: {selector}")
    return selected
