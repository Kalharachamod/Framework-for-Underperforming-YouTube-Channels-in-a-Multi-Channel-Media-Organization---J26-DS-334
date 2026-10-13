"""Minimal YouTube Data API v3 client for manual collection."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


@dataclass
class YouTubeApiError(Exception):
    message: str
    status: int | None = None
    reason: str | None = None
    retryable: bool = False
    quota_exhausted: bool = False

    def __str__(self) -> str:
        reason = f" ({self.reason})" if self.reason else ""
        status = f" HTTP {self.status}" if self.status else ""
        return f"{self.message}{status}{reason}"


class YouTubeClient:
    def __init__(self, api_key: str, max_retries: int = 3, timeout: int = 30) -> None:
        if not api_key:
            raise ValueError("YOUTUBE_API_KEY is required")
        self._api_key = api_key
        self.max_retries = max_retries
        self.timeout = timeout
        self.request_count = 0

    def channels_list(self, **params: Any) -> dict[str, Any]:
        return self._get("channels", params)

    def playlist_items_list(self, **params: Any) -> dict[str, Any]:
        return self._get("playlistItems", params)

    def comment_threads_list(self, **params: Any) -> dict[str, Any]:
        return self._get("commentThreads", params)

    def comments_list(self, **params: Any) -> dict[str, Any]:
        return self._get("comments", params)

    def _get(self, resource: str, params: dict[str, Any]) -> dict[str, Any]:
        query = {k: v for k, v in params.items() if v is not None}
        query["key"] = self._api_key
        url = f"{YOUTUBE_API_BASE}/{resource}?{urlencode(query)}"

        for attempt in range(self.max_retries + 1):
            try:
                self.request_count += 1
                request = Request(url, headers={"Accept": "application/json"})
                with urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                api_error = self._parse_http_error(exc)
                if not api_error.retryable or attempt >= self.max_retries:
                    raise api_error from exc
                time.sleep(2**attempt)
            except URLError as exc:
                if attempt >= self.max_retries:
                    raise YouTubeApiError(
                        f"YouTube API request failed: {exc.reason}",
                        retryable=True,
                    ) from exc
                time.sleep(2**attempt)

        raise YouTubeApiError("YouTube API request failed after retries")

    @staticmethod
    def _parse_http_error(exc: HTTPError) -> YouTubeApiError:
        body = exc.read().decode("utf-8", errors="replace")
        reason = None
        message = body or exc.reason
        try:
            payload = json.loads(body)
            errors = payload.get("error", {}).get("errors", [])
            reason = errors[0].get("reason") if errors else None
            message = payload.get("error", {}).get("message", message)
        except json.JSONDecodeError:
            pass

        quota_reasons = {"quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"}
        retryable_reasons = {"backendError", "internalError", "rateLimitExceeded"}
        quota_exhausted = reason in quota_reasons
        retryable = exc.code in {429, 500, 502, 503, 504} or reason in retryable_reasons
        if reason in {"quotaExceeded", "dailyLimitExceeded"}:
            retryable = False

        return YouTubeApiError(
            message=message,
            status=exc.code,
            reason=reason,
            retryable=retryable,
            quota_exhausted=quota_exhausted,
        )
