"""Public channel icons for the Component 3 dashboard (presentation metadata, not research data).

    python -m research.component_3.preprocessing.channel_icons            # channels of every research snapshot

Reads the channel ids of the research snapshots, asks the YouTube Data API ``channels.list``
(part=snippet; 1 quota unit per 50 channels) for each channel's public profile image URL and
writes ``data/processed/component_3/channel_icons.json``::

    {"fetched_at": "...", "items": {"<channel_id>": "https://yt3.ggpht.com/..."}}

Only public channel-level data is stored: no commenter, video or account data. The URLs are
not used by any score, feature or evaluation. Only image hosts on ``ALLOWED_HOSTS`` are kept, so
the dashboard never loads an image from an unexpected domain.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from shared.data_collection.youtube_api_client import YouTubeClient
from shared.utils import snapshots
from shared.utils.parquet_io import read_dataset
from shared.utils.paths import component_dir

ALLOWED_HOSTS = {"yt3.ggpht.com", "yt3.googleusercontent.com", "i.ytimg.com"}
SIZES = ("medium", "default", "high")
BATCH = 50
CHANNEL_ID = re.compile(r"UC[A-Za-z0-9_-]{22}")


def is_channel_id(value: object) -> bool:
    return isinstance(value, str) and CHANNEL_ID.fullmatch(value) is not None


def icons_path() -> Path:
    return component_dir(3) / "channel_icons.json"


def snapshot_channel_ids() -> list[str]:
    """Channel ids of every research snapshot, deduplicated and sorted."""
    ids: set[str] = set()
    for info in snapshots.list_research_snapshots():
        df = read_dataset(snapshots.research_dataset_path(info.snapshot_id, "channels"), columns=["channel_id"])
        ids.update(str(c) for c in df["channel_id"].dropna())
    return sorted(i for i in ids if is_channel_id(i))


def icon_url(item: dict[str, Any]) -> str | None:
    """The profile image URL of a ``channels.list`` item, if it is on an allowed https host."""
    thumbs = (item.get("snippet") or {}).get("thumbnails") or {}
    for size in SIZES:
        url = (thumbs.get(size) or {}).get("url")
        if isinstance(url, str):
            parsed = urlparse(url)
            if parsed.scheme == "https" and parsed.hostname in ALLOWED_HOSTS:
                return url
    return None


def fetch_icons(client: YouTubeClient, channel_ids: Iterable[str]) -> dict[str, str]:
    ids = list(channel_ids)
    out: dict[str, str] = {}
    for start in range(0, len(ids), BATCH):
        response = client.channels_list(part="snippet", id=ids[start:start + BATCH])
        for item in response.items:
            cid, url = item.get("id"), icon_url(item)
            if is_channel_id(cid) and url:
                out[cid] = url
    return out


def write_icons(icons: dict[str, str], path: Path | None = None) -> Path:
    path = path or icons_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"fetched_at": datetime.now(timezone.utc).isoformat(), "items": dict(sorted(icons.items()))}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def main(argv: Iterable[str] | None = None) -> int:
    ids = snapshot_channel_ids()
    if not ids:
        print("no research snapshot channels found", file=sys.stderr)
        return 1
    client = YouTubeClient()
    icons = fetch_icons(client, ids)
    path = write_icons(icons)
    print(f"{len(icons)} of {len(ids)} channel icons written to {path} (quota used: {client.quota_used})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
