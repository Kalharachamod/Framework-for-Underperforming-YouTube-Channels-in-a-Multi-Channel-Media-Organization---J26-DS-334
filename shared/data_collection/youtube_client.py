"""Minimal read-only YouTube Data API v3 client.

Only the calls the project needs, with quota accounting. The API key is read
from ``YOUTUBE_API_KEY`` (``.env``) and is never included in errors or logs.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from typing import Any

from shared.utils import paths  # noqa: F401  (loads .env)

# Quota cost per request (YouTube Data API v3).
COST = {"search.list": 100, "channels.list": 1, "channelSections.list": 1}
DAILY_QUOTA = 10_000

_KEY_IN_TEXT = re.compile(r"(key=)[^&\s\"']+")


class YouTubeAPIError(RuntimeError):
    """A YouTube API request failed. ``reason`` is e.g. 'quotaExceeded' or 'keyInvalid'."""

    def __init__(self, message: str, reason: str | None = None, status: int | None = None):
        super().__init__(message)
        self.reason = reason
        self.status = status


class YouTubeClient:
    """Thin wrapper over ``googleapiclient`` for public, read-only data."""

    def __init__(self, api_key: str | None = None, *, service: Any = None):
        self.quota_used = 0
        if service is not None:  # injected (tests)
            self._yt = service
            return
        key = api_key or os.getenv("YOUTUBE_API_KEY", "")
        if not key:
            raise YouTubeAPIError("YOUTUBE_API_KEY is not set; add it to .env", reason="missingKey")
        from googleapiclient.discovery import build

        self._yt = build("youtube", "v3", developerKey=key, cache_discovery=False, static_discovery=True)

    # --- endpoints -----------------------------------------------------------------

    def search_channels(self, query: str, *, max_results: int = 25, region_code: str | None = None) -> list[str]:
        """Channel ids matching ``query`` (100 quota units)."""
        if not query or not query.strip():
            raise ValueError("query must not be empty")
        params = {"part": "snippet", "q": query.strip(), "type": "channel", "maxResults": min(max_results, 50)}
        if region_code:
            params["regionCode"] = region_code
        response = self._call("search.list", self._yt.search().list(**params))
        return [item["id"]["channelId"] for item in response.get("items", []) if item.get("id", {}).get("channelId")]

    def get_channels(self, channel_ids: Iterable[str]) -> list[dict[str, Any]]:
        """Channel resources (snippet, statistics, brandingSettings); 1 unit per 50 ids."""
        ids = list(dict.fromkeys(channel_ids))
        items: list[dict[str, Any]] = []
        for start in range(0, len(ids), 50):
            batch = ids[start:start + 50]
            request = self._yt.channels().list(
                part="snippet,statistics,brandingSettings", id=",".join(batch), maxResults=50
            )
            items.extend(self._call("channels.list", request).get("items", []))
        return items

    def get_linked_channels(self, channel_id: str) -> list[str]:
        """Channels a channel lists in its multi-channel/featured sections (1 unit)."""
        request = self._yt.channelSections().list(part="contentDetails,snippet", channelId=channel_id)
        response = self._call("channelSections.list", request)
        linked: list[str] = []
        for section in response.get("items", []):
            for cid in section.get("contentDetails", {}).get("channels", []) or []:
                if cid != channel_id and cid not in linked:
                    linked.append(cid)
        return linked

    # --- internals -------------------------------------------------------------------

    def _call(self, endpoint: str, request: Any) -> dict[str, Any]:
        self.quota_used += COST[endpoint]
        try:
            return request.execute(num_retries=2)
        except Exception as exc:  # googleapiclient.errors.HttpError and network errors
            raise _sanitized_error(endpoint, exc) from None


def _sanitized_error(endpoint: str, exc: Exception) -> YouTubeAPIError:
    status = getattr(getattr(exc, "resp", None), "status", None)
    reason = None
    details = getattr(exc, "error_details", None)
    if isinstance(details, list) and details and isinstance(details[0], dict):
        reason = details[0].get("reason")
    text = _KEY_IN_TEXT.sub(r"\1***", str(exc))
    message = f"{endpoint} failed"
    if status:
        message += f" (HTTP {status})"
    if reason:
        message += f": {reason}"
    if reason == "quotaExceeded":
        message += " - daily quota used up; try again after midnight Pacific Time"
    return YouTubeAPIError(f"{message}. {text}", reason=reason, status=status)
