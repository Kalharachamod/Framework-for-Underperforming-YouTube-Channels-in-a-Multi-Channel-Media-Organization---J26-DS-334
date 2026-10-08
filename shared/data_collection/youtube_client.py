"""Secure, read-only YouTube Data API v3 client.

YouTube Data API v3 is the project's only external data source. This module is
the low-level access layer: it validates request parameters, sends HTTPS GET
requests, retries transient failures, raises structured errors and records
every request with its quota cost. It returns raw API resources; turning them
into research schemas is the job of the collectors (later step).

The API key comes from ``YOUTUBE_API_KEY`` in ``.env``. It is never logged,
printed, stored or included in any exception message.
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from shared.utils import paths  # noqa: F401  (loads .env)

log = logging.getLogger(__name__)

BASE_URL = "https://www.googleapis.com/youtube/v3"
DAILY_QUOTA = 10_000  # default daily quota of a Google Cloud project

# Quota units per request (YouTube Data API v3 documentation).
COST = {"channels": 1, "videos": 1, "commentThreads": 1, "channelSections": 1, "search": 100}

ALLOWED_PARTS = {
    "channels": {"id", "snippet", "statistics", "brandingSettings", "contentDetails", "topicDetails",
                 "status", "localizations"},
    "videos": {"id", "snippet", "statistics", "contentDetails", "status", "topicDetails",
               "liveStreamingDetails", "localizations", "recordingDetails"},
    "commentThreads": {"id", "snippet", "replies"},
    "channelSections": {"id", "snippet", "contentDetails"},
    "search": {"id", "snippet"},
}
MAX_RESULTS = {"channels": 50, "videos": 50, "commentThreads": 100, "channelSections": None, "search": 50}

PLACEHOLDER_KEYS = {"", "your_youtube_api_key_here", "changeme", "xxx"}
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
RATE_LIMIT_REASONS = {"rateLimitExceeded", "userRateLimitExceeded"}
QUOTA_REASONS = {"quotaExceeded", "dailyLimitExceeded"}
KEY_REASONS = {"keyInvalid", "keyExpired", "accessNotConfigured", "ipRefererBlocked", "forbiddenByRestrictions"}

_ID = re.compile(r"^[A-Za-z0-9_.\-]{1,128}$")
_PAGE_TOKEN = re.compile(r"^[A-Za-z0-9_\-=]{1,512}$")
_KEY_IN_TEXT = re.compile(r"(key=)[^&\s\"']+")


class _Secret:
    """Holds the API key; shows as *** in repr, str, vars() and debuggers."""

    __slots__ = ("_value",)

    def __init__(self, value: str):
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "<secret ***>"

    __str__ = __repr__


# --- errors ----------------------------------------------------------------------

class YouTubeAPIError(RuntimeError):
    """Base error. ``status`` = HTTP status, ``reason`` = YouTube error reason."""

    retryable = False

    def __init__(self, message: str, *, status: int | None = None, reason: str | None = None,
                 resource: str | None = None):
        super().__init__(message)
        self.status = status
        self.reason = reason
        self.resource = resource


class MissingAPIKeyError(YouTubeAPIError):
    """YOUTUBE_API_KEY is not set (or still the placeholder)."""


class InvalidAPIKeyError(YouTubeAPIError):
    """The key is wrong, expired, restricted, or the API is not enabled for it."""


class QuotaExceededError(YouTubeAPIError):
    """Daily quota used up. Not retried: it resets at midnight Pacific Time."""


class RateLimitError(YouTubeAPIError):
    """Too many requests in a short time (HTTP 429 or rateLimitExceeded). Retried."""

    retryable = True


class BadRequestError(YouTubeAPIError):
    """HTTP 400: the request is invalid."""


class UnauthorizedError(YouTubeAPIError):
    """HTTP 401: authorization required (not expected for public data)."""


class ForbiddenError(YouTubeAPIError):
    """HTTP 403 for other reasons, e.g. commentsDisabled, forbidden."""


class NotFoundError(YouTubeAPIError):
    """HTTP 404, e.g. videoNotFound, channelNotFound."""


class ServerError(YouTubeAPIError):
    """HTTP 5xx: temporary YouTube problem. Retried."""

    retryable = True


class NetworkError(YouTubeAPIError):
    """Connection failure. Retried."""

    retryable = True


class APITimeoutError(NetworkError):
    """The request timed out. Retried."""


class MalformedResponseError(YouTubeAPIError):
    """The API answered with something that is not a valid list response."""


class RequestValidationError(ValueError):
    """Invalid request parameters; detected before anything is sent."""


# --- results and request log -----------------------------------------------------

@dataclass(frozen=True)
class ApiResponse:
    """One page of a ``*.list`` response, kept close to the API format."""

    resource: str
    items: list[dict[str, Any]]
    next_page_token: str | None
    prev_page_token: str | None
    page_info: dict[str, Any]
    quota_cost: int
    raw: dict[str, Any]


@dataclass(frozen=True)
class RequestRecord:
    """What happened to one request; never contains the API key."""

    resource: str
    method: str
    succeeded: bool
    quota_cost: int
    attempts: int
    http_status: int | None
    error: str | None
    at: str


@dataclass
class HttpResult:
    status: int
    headers: Mapping[str, str]
    body: bytes


Transport = Callable[[str, dict[str, str], float], HttpResult]


def urllib_transport(url: str, params: dict[str, str], timeout: float) -> HttpResult:
    """Default transport: HTTPS GET with urllib; parameters are URL-encoded safely."""
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(full_url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return HttpResult(resp.status, dict(resp.headers), resp.read())
    except urllib.error.HTTPError as exc:  # 4xx / 5xx still carry a JSON body
        return HttpResult(exc.code, dict(exc.headers or {}), exc.read() or b"")


# --- client ---------------------------------------------------------------------

@dataclass
class RetryPolicy:
    max_retries: int = 3          # retries after the first attempt
    backoff_seconds: float = 1.0  # 1, 2, 4, ... (+ up to 10% jitter)
    max_backoff_seconds: float = 30.0


class YouTubeClient:
    """Low-level, read-only client. Every ``*_list`` method returns an ``ApiResponse``."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        timeout: float = 30.0,
        retry: RetryPolicy | None = None,
        transport: Transport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        key = (api_key if api_key is not None else os.getenv("YOUTUBE_API_KEY", "")).strip()
        if key.lower() in PLACEHOLDER_KEYS:
            raise MissingAPIKeyError("YOUTUBE_API_KEY is not set; copy .env.example to .env and add your key")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._key = _Secret(key)
        self.timeout = timeout
        self.retry = retry or RetryPolicy()
        self._transport = transport or urllib_transport
        self._sleep = sleep
        self.request_log: list[RequestRecord] = []

    def __repr__(self) -> str:  # never show the key
        return f"YouTubeClient(timeout={self.timeout}, quota_used={self.quota_used})"

    @property
    def quota_used(self) -> int:
        """Estimated quota units spent by this client (requests the API answered)."""
        return sum(r.quota_cost for r in self.request_log)

    # --- endpoints ------------------------------------------------------------------

    def channels_list(self, *, part: Iterable[str] | str, id: Iterable[str] | str | None = None,
                      for_handle: str | None = None, max_results: int | None = None,
                      page_token: str | None = None) -> ApiResponse:
        """channels.list by ids (up to 50) or by handle (``@name``). 1 unit."""
        params = self._base("channels", part, max_results, page_token)
        if (id is None) == (for_handle is None):
            raise RequestValidationError("channels.list needs exactly one of id or for_handle")
        if id is not None:
            params["id"] = _ids(id, "id", limit=50)
        else:
            handle = (for_handle or "").strip()
            if not re.fullmatch(r"@?[A-Za-z0-9_.\-]{3,100}", handle):
                raise RequestValidationError(f"invalid handle: {for_handle!r}")
            params["forHandle"] = handle
        return self._list("channels", params)

    def videos_list(self, *, part: Iterable[str] | str, id: Iterable[str] | str) -> ApiResponse:
        """videos.list for up to 50 video ids. 1 unit."""
        params = self._base("videos", part, None, None)
        params["id"] = _ids(id, "id", limit=50)
        return self._list("videos", params)

    def comment_threads_list(self, *, part: Iterable[str] | str = "snippet", video_id: str | None = None,
                             all_threads_related_to_channel_id: str | None = None,
                             max_results: int | None = None, page_token: str | None = None,
                             order: str | None = None, text_format: str | None = None) -> ApiResponse:
        """commentThreads.list for one video or channel (up to 100 per page). 1 unit."""
        params = self._base("commentThreads", part, max_results, page_token)
        if (video_id is None) == (all_threads_related_to_channel_id is None):
            raise RequestValidationError("commentThreads.list needs exactly one of video_id or "
                                         "all_threads_related_to_channel_id")
        if video_id is not None:
            params["videoId"] = _ids(video_id, "video_id", limit=1)
        else:
            params["allThreadsRelatedToChannelId"] = _ids(all_threads_related_to_channel_id,
                                                          "all_threads_related_to_channel_id", limit=1)
        if order is not None:
            params["order"] = _choice(order, {"time", "relevance"}, "order")
        if text_format is not None:
            params["textFormat"] = _choice(text_format, {"plainText", "html"}, "text_format")
        return self._list("commentThreads", params)

    def search_list(self, *, q: str | None = None, channel_id: str | None = None, type: str = "video",
                    part: Iterable[str] | str = "snippet", max_results: int | None = None,
                    page_token: str | None = None, order: str | None = None,
                    region_code: str | None = None, published_after: str | None = None) -> ApiResponse:
        """search.list. Expensive: 100 units per call; prefer other endpoints."""
        params = self._base("search", part, max_results, page_token)
        if not (q and q.strip()) and channel_id is None:
            raise RequestValidationError("search.list needs q or channel_id")
        if q is not None:
            if not q.strip() or len(q) > 500:
                raise RequestValidationError("q must be 1-500 characters")
            params["q"] = q.strip()
        if channel_id is not None:
            params["channelId"] = _ids(channel_id, "channel_id", limit=1)
        params["type"] = _choice(type, {"channel", "video", "playlist"}, "type")
        if order is not None:
            params["order"] = _choice(order, {"date", "rating", "relevance", "title", "videoCount", "viewCount"},
                                      "order")
        if region_code is not None:
            if not re.fullmatch(r"[A-Za-z]{2}", region_code):
                raise RequestValidationError("region_code must be a 2-letter country code")
            params["regionCode"] = region_code.upper()
        if published_after is not None:
            try:
                datetime.fromisoformat(published_after.replace("Z", "+00:00"))
            except ValueError:
                raise RequestValidationError("published_after must be an RFC 3339 timestamp") from None
            params["publishedAfter"] = published_after
        return self._list("search", params)

    def channel_sections_list(self, *, channel_id: str,
                              part: Iterable[str] | str = "contentDetails,snippet") -> ApiResponse:
        """channelSections.list (featured / multi-channel sections). 1 unit."""
        params = self._base("channelSections", part, None, None)
        params["channelId"] = _ids(channel_id, "channel_id", limit=1)
        return self._list("channelSections", params)

    # --- conveniences used by organization discovery --------------------------------

    def search_channels(self, query: str, *, max_results: int = 25, region_code: str | None = None) -> list[str]:
        """Channel ids matching ``query`` (100 units)."""
        if not query or not query.strip():
            raise ValueError("query must not be empty")
        response = self.search_list(q=query, type="channel", max_results=min(max_results, 50),
                                    region_code=region_code)
        return [i["id"]["channelId"] for i in response.items if i.get("id", {}).get("channelId")]

    def get_channels(self, channel_ids: Iterable[str]) -> list[dict[str, Any]]:
        """Channel resources (snippet, statistics, brandingSettings); 1 unit per 50 ids."""
        ids = list(dict.fromkeys(channel_ids))
        items: list[dict[str, Any]] = []
        for start in range(0, len(ids), 50):
            items += self.channels_list(part="snippet,statistics,brandingSettings", id=ids[start:start + 50]).items
        return items

    def get_linked_channels(self, channel_id: str) -> list[str]:
        """Channels listed in a channel's featured / multi-channel sections (1 unit)."""
        linked: list[str] = []
        for section in self.channel_sections_list(channel_id=channel_id).items:
            for cid in section.get("contentDetails", {}).get("channels", []) or []:
                if cid != channel_id and cid not in linked:
                    linked.append(cid)
        return linked

    # --- internals -------------------------------------------------------------------

    def _base(self, resource: str, part, max_results, page_token) -> dict[str, str]:
        params = {"part": _parts(part, resource)}
        if max_results is not None:
            limit = MAX_RESULTS[resource]
            if limit is None:
                raise RequestValidationError(f"{resource}.list does not take max_results")
            low = 0 if resource == "search" else 1
            if isinstance(max_results, bool) or not isinstance(max_results, int) or not low <= max_results <= limit:
                raise RequestValidationError(f"max_results for {resource}.list must be {low}-{limit}, got {max_results!r}")
            params["maxResults"] = str(max_results)
        if page_token is not None:
            if not isinstance(page_token, str) or not _PAGE_TOKEN.fullmatch(page_token):
                raise RequestValidationError("page_token must be a token returned by a previous response")
            params["pageToken"] = page_token
        return params

    def _list(self, resource: str, params: dict[str, str]) -> ApiResponse:
        cost = COST[resource]
        attempts = 0
        while True:
            attempts += 1
            try:
                result = self._send(resource, params)
                data = _interpret(resource, result, self._key.reveal())
            except YouTubeAPIError as exc:
                answered = exc.status is not None
                if exc.retryable and attempts <= self.retry.max_retries:
                    delay = self._delay(attempts, exc)
                    log.warning("%s.list attempt %d failed (%s); retrying in %.1fs",
                                resource, attempts, type(exc).__name__, delay)
                    self._record(resource, False, cost if answered else 0, attempts, exc)
                    self._sleep(delay)
                    continue
                self._record(resource, False, cost if answered else 0, attempts, exc)
                raise
            self._record(resource, True, cost, attempts, None)
            return ApiResponse(
                resource=resource,
                items=data.get("items", []),
                next_page_token=data.get("nextPageToken"),
                prev_page_token=data.get("prevPageToken"),
                page_info=data.get("pageInfo", {}),
                quota_cost=cost,
                raw=data,
            )

    def _send(self, resource: str, params: dict[str, str]) -> HttpResult:
        """Call the transport; network failures become structured, key-free errors."""
        try:
            return self._transport(f"{BASE_URL}/{resource}", {**params, "key": self._key.reveal()}, self.timeout)
        except (TimeoutError, socket.timeout):
            raise APITimeoutError(f"{resource}.list timed out after {self.timeout}s", resource=resource) from None
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise APITimeoutError(f"{resource}.list timed out after {self.timeout}s", resource=resource) from None
            raise NetworkError(f"{resource}.list connection failed: {_redact(str(exc.reason), self._key.reveal())}",
                               resource=resource) from None
        except OSError as exc:  # ConnectionError, DNS failure, ...
            raise NetworkError(f"{resource}.list connection failed: {type(exc).__name__}: "
                               f"{_redact(str(exc), self._key.reveal())}", resource=resource) from None

    def _delay(self, attempt: int, exc: YouTubeAPIError) -> float:
        retry_after = getattr(exc, "retry_after", None)
        base = retry_after if retry_after is not None else self.retry.backoff_seconds * 2 ** (attempt - 1)
        base = min(base, self.retry.max_backoff_seconds)
        return base + random.uniform(0, base * 0.1)

    def _record(self, resource, succeeded, cost, attempts, exc) -> None:
        self.request_log.append(RequestRecord(
            resource=resource, method="list", succeeded=succeeded, quota_cost=cost, attempts=attempts,
            http_status=getattr(exc, "status", None) if exc else 200,
            error=None if exc is None else (getattr(exc, "reason", None) or type(exc).__name__),
            at=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        ))


def _interpret(resource: str, result: HttpResult, key: str) -> dict[str, Any]:
    if not isinstance(result, HttpResult):
        raise MalformedResponseError(f"{resource}.list: transport returned no HTTP result", resource=resource)
    payload: Any = None
    try:
        payload = json.loads(result.body.decode("utf-8")) if result.body else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = None

    if 200 <= result.status < 300:
        if not isinstance(payload, dict):
            raise MalformedResponseError(f"{resource}.list: response is not a JSON object",
                                         status=result.status, resource=resource)
        if "items" in payload and not isinstance(payload["items"], list):
            raise MalformedResponseError(f"{resource}.list: 'items' is not a list",
                                         status=result.status, resource=resource)
        return payload

    raise _http_error(resource, result, payload, key)


def _http_error(resource: str, result: HttpResult, payload: Any, key: str) -> YouTubeAPIError:
    error = payload.get("error", {}) if isinstance(payload, dict) else {}
    errors = error.get("errors") if isinstance(error, dict) else None
    reason = errors[0].get("reason") if isinstance(errors, list) and errors and isinstance(errors[0], dict) else None
    detail = _redact(str(error.get("message", "")) if isinstance(error, dict) else "", key)
    status = result.status
    where = f"{resource}.list failed (HTTP {status}{', ' + reason if reason else ''})"
    message = f"{where}: {detail}" if detail else where
    kwargs = {"status": status, "reason": reason, "resource": resource}

    if reason in QUOTA_REASONS:
        return QuotaExceededError(message + " - daily quota used up; it resets at midnight Pacific Time", **kwargs)
    if reason in KEY_REASONS or (status == 400 and "api key" in detail.lower()):
        return InvalidAPIKeyError(message + " - check YOUTUBE_API_KEY in .env and that YouTube Data API v3 "
                                  "is enabled for it", **kwargs)
    if status == 429 or reason in RATE_LIMIT_REASONS:
        exc = RateLimitError(message, **kwargs)
        exc.retry_after = _retry_after(result.headers)
        return exc
    if status >= 500:
        return ServerError(message, **kwargs)
    return {400: BadRequestError, 401: UnauthorizedError, 403: ForbiddenError, 404: NotFoundError}.get(
        status, YouTubeAPIError)(message, **kwargs)


def _retry_after(headers: Mapping[str, str]) -> float | None:
    value = next((v for k, v in headers.items() if k.lower() == "retry-after"), None)
    try:
        return max(0.0, float(value)) if value is not None else None
    except ValueError:
        return None


def _redact(text: str, key: str) -> str:
    text = _KEY_IN_TEXT.sub(r"\1***", text)
    return text.replace(key, "***") if key else text


# --- parameter helpers --------------------------------------------------------------

def is_valid_id(value: Any) -> bool:
    """True for a well-formed channel / video / comment id (format only)."""
    return isinstance(value, str) and bool(_ID.fullmatch(value))



def _parts(part, resource: str) -> str:
    items = [p.strip() for p in (part.split(",") if isinstance(part, str) else list(part or []))]
    items = [p for p in items if p]
    if not items:
        raise RequestValidationError(f"{resource}.list needs at least one part")
    bad = sorted(set(items) - ALLOWED_PARTS[resource])
    if bad:
        raise RequestValidationError(f"invalid part(s) for {resource}.list: {bad}")
    return ",".join(dict.fromkeys(items))


def _ids(value, name: str, *, limit: int) -> str:
    items = value.split(",") if isinstance(value, str) else list(value or [])
    items = [i.strip() if isinstance(i, str) else i for i in items]
    if not items or any(not isinstance(i, str) or not _ID.fullmatch(i) for i in items):
        raise RequestValidationError(f"{name} must be non-empty YouTube id(s), got {value!r}")
    if len(items) > limit:
        raise RequestValidationError(f"{name} accepts at most {limit} id(s), got {len(items)}")
    return ",".join(dict.fromkeys(items))


def _choice(value: str, allowed: set[str], name: str) -> str:
    if value not in allowed:
        raise RequestValidationError(f"{name} must be one of {sorted(allowed)}, got {value!r}")
    return value
