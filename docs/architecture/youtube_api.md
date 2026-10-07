# YouTube Data API v3 Client

Code: [`shared/data_collection/youtube_client.py`](../../shared/data_collection/youtube_client.py) · Tests: [`tests/shared/test_youtube_client.py`](../../tests/shared/test_youtube_client.py) (mocked HTTP, no real calls)

## External data source

The project's only external data source is the **official YouTube Data API v3** (`https://www.googleapis.com/youtube/v3`). Only **public** data is read (channels, videos, comment threads), using an **API key**; no user sign-in (OAuth) is needed. The client is the low-level access layer: it returns API resources unchanged. Converting them into research schemas is the job of the collectors (a later step).

## API key setup

1. Open the [Google Cloud Console](https://console.cloud.google.com/) and create a project, or select one.
2. **APIs & Services → Library →** search "YouTube Data API v3" → **Enable**.
3. **APIs & Services → Credentials → Create credentials → API key.**
4. Restrict the key: **API restrictions → YouTube Data API v3**.
5. Put the key in your local `.env`:

```powershell
Copy-Item .env.example .env     # once
# edit .env (NOT .env.example):
YOUTUBE_API_KEY=<your real key>
```

| File | Purpose | In git? |
|---|---|---|
| `.env` | Your real key and secrets | **Never**; ignored by `.gitignore` |
| `.env.example` | Template with placeholders only (`YOUTUBE_API_KEY=your_youtube_api_key_here`) | Yes |

The client refuses to start if the key is missing or still the placeholder (`MissingAPIKeyError`).

**Never** put the real key in code, tests, notebooks, docs, screenshots, chat or `.env.example`. If it leaks, delete it in the Cloud Console and create a new one.

## Basic usage

```python
from shared.data_collection.youtube_client import YouTubeClient

client = YouTubeClient()                       # reads YOUTUBE_API_KEY from .env

r = client.channels_list(part="snippet,statistics", id=["UC...", "UC..."])   # up to 50 ids
r = client.videos_list(part="snippet,statistics", id=video_ids)             # up to 50 ids
r = client.comment_threads_list(video_id="VIDEO_ID", max_results=100, order="time")
r = client.comment_threads_list(video_id="VIDEO_ID", max_results=100, page_token=r.next_page_token)
r = client.search_list(q="Derana", type="channel")                          # 100 units!

r.items            # list of API resources, unchanged
r.next_page_token  # pass back as page_token for the next page (None on the last page)
r.page_info        # {"totalResults": ..., "resultsPerPage": ...}
r.quota_cost       # units this request cost
```

Pagination: the client sends one page per call. Pass `page_token=` and `max_results=` yourself. Looping over pages belongs to the collectors.

## Request validation

Parameters are checked **before** anything is sent; problems raise `RequestValidationError` (a `ValueError`) and cost no quota:
- `part` must be present and valid for the resource.
- IDs must be non-empty and well-formed: up to 50 for channels and videos, exactly one target for comment threads.
- `max_results` must be within the API's limits: 1–50, 1–100 for comment threads, 0–50 for search.
- `order`, `text_format`, `type`, `region_code` and `published_after` must be allowed values.
- `page_token` must look like a token returned by the API.

Query parameters are URL-encoded by the HTTP library, never concatenated by hand.

## Errors

All API errors are subclasses of `YouTubeAPIError`, with `.status` (HTTP), `.reason` (YouTube reason) and `.resource`:

| Error | When | Retried? |
|---|---|---|
| `MissingAPIKeyError` | Key missing or placeholder | n/a |
| `InvalidAPIKeyError` | Key invalid, expired or restricted, or the API isn't enabled | No |
| `QuotaExceededError` | Daily quota used up (`quotaExceeded`) | No; resets at midnight Pacific Time |
| `RateLimitError` | HTTP 429, or `rateLimitExceeded` | **Yes** (honours `Retry-After`) |
| `BadRequestError` | HTTP 400 | No |
| `UnauthorizedError` | HTTP 401 | No |
| `ForbiddenError` | HTTP 403, e.g. `commentsDisabled` | No |
| `NotFoundError` | HTTP 404, e.g. `videoNotFound` | No |
| `ServerError` | HTTP 500/502/503/504 | **Yes** |
| `APITimeoutError` / `NetworkError` | Timeout, connection or DNS failure | **Yes** |
| `MalformedResponseError` | Not JSON, not an object, or `items` not a list | No |

**Retries** apply only to the transient cases above: by default up to **3 retries** with exponential backoff of 1 s, 2 s, then 4 s, plus up to 10% jitter, capped at 30 s. Errors are never hidden; when retries run out, the last error is raised. Collectors decide what to do. For example, `commentsDisabled` means skip that video, and `QuotaExceededError` means stop and continue tomorrow.

## Quota awareness

The API isn't unlimited: a project gets **10,000 units per day** by default.

| Request | Cost |
|---|---|
| `channels.list`, `videos.list`, `commentThreads.list`, `channelSections.list` | 1 unit |
| `search.list` | **100 units**; avoid it where possible |

The client records every request in `client.request_log`: resource, method, success, quota cost, attempts, HTTP status, error reason and time. `client.quota_used` is the running estimate; failed requests that the API answered also count. Neither contains the key.

## Security

- The key is read only from the environment (`.env`), held in a wrapper that always displays as `***`, and sent only as a request parameter over HTTPS.
- It's removed from every error message, including Google's own error text and network errors, and exceptions are raised without chained low-level errors that could contain the request URL.
- It never appears in `repr(client)`, `vars(client)`, logs or the request log; tests check all of these.

## Tests

```powershell
python -m pytest tests/shared/test_youtube_client.py   # client only
python -m pytest                                       # everything
```
The tests replace the HTTP layer with a mock, so they make **no real API calls and use no quota**. They cover the missing key, success, malformed responses, HTTP 400/401/403/404/429/5xx, timeouts, network failures, the retry behaviour and limit, parameter validation, pagination, and key leakage.
