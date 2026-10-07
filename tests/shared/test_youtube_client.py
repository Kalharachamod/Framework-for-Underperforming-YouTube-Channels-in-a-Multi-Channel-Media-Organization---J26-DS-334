"""Tests for the YouTube Data API v3 client.

Every test uses a mocked HTTP transport: no real API calls, no quota used.
The key "TEST_KEY_abc123" is a fake used to prove the key never leaks.
"""

import json
import logging
import socket
import urllib.error

import pytest

from shared.data_collection import youtube_client as yc
from shared.data_collection.youtube_client import HttpResult, RetryPolicy, YouTubeClient

KEY = "TEST_KEY_abc123"


class MockTransport:
    """Returns queued responses (HttpResult) or raises queued exceptions."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, params, timeout):
        self.calls.append({"url": url, "params": dict(params), "timeout": timeout})
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, BaseException):
            raise item
        return item


def ok(body=None, status=200, headers=None):
    return HttpResult(status, headers or {}, json.dumps(body if body is not None else {"items": []}).encode())


def api_error(status, reason=None, message="error", headers=None):
    errors = [{"reason": reason, "domain": "youtube"}] if reason else []
    return HttpResult(status, headers or {}, json.dumps({"error": {"code": status, "message": message,
                                                                    "errors": errors}}).encode())


def make(*responses, retries=3):
    transport = MockTransport(*responses)
    sleeps = []
    client = YouTubeClient(api_key=KEY, transport=transport, sleep=sleeps.append,
                           retry=RetryPolicy(max_retries=retries, backoff_seconds=1, max_backoff_seconds=8))
    return client, transport, sleeps


# --- configuration -----------------------------------------------------------------

@pytest.mark.parametrize("value", [None, "", "   ", "your_youtube_api_key_here"])
def test_missing_or_placeholder_key(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    else:
        monkeypatch.setenv("YOUTUBE_API_KEY", value)
    with pytest.raises(yc.MissingAPIKeyError, match="YOUTUBE_API_KEY is not set"):
        YouTubeClient(transport=MockTransport(ok()))


def test_valid_configuration_from_environment(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", KEY)
    transport = MockTransport(ok())
    client = YouTubeClient(transport=transport)
    client.channels_list(part="snippet", id="UC_test")
    assert transport.calls[0]["params"]["key"] == KEY
    assert transport.calls[0]["url"] == "https://www.googleapis.com/youtube/v3/channels"
    assert transport.calls[0]["timeout"] == 30.0


def test_invalid_timeout():
    with pytest.raises(ValueError):
        YouTubeClient(api_key=KEY, timeout=0)


def test_repr_hides_key():
    client, _, _ = make(ok())
    assert KEY not in repr(client) and KEY not in str(vars(client))


# --- successful requests ---------------------------------------------------------------

def test_successful_request_structured_response():
    body = {"kind": "youtube#commentThreadListResponse", "nextPageToken": "NEXT_tok",
            "pageInfo": {"totalResults": 2, "resultsPerPage": 1}, "items": [{"id": "c1"}]}
    client, transport, _ = make(ok(body))
    r = client.comment_threads_list(video_id="vid_1", max_results=1, order="time", text_format="plainText")

    assert r.resource == "commentThreads"
    assert r.items == [{"id": "c1"}]
    assert r.next_page_token == "NEXT_tok" and r.prev_page_token is None
    assert r.page_info == {"totalResults": 2, "resultsPerPage": 1}
    assert r.quota_cost == 1 and r.raw["kind"] == "youtube#commentThreadListResponse"
    sent = transport.calls[0]["params"]
    assert sent == {"part": "snippet", "maxResults": "1", "videoId": "vid_1", "order": "time",
                    "textFormat": "plainText", "key": KEY}


def test_each_endpoint_builds_expected_params():
    client, transport, _ = make(ok())
    client.channels_list(part=["snippet", "statistics"], id=["UC_a", "UC_b"])
    client.channels_list(part="id", for_handle="@testhandle")
    client.videos_list(part="snippet,statistics", id="v1,v2")
    client.comment_threads_list(all_threads_related_to_channel_id="UC_a")
    client.search_list(q="test", type="channel", max_results=5, region_code="lk",
                       published_after="2026-01-01T00:00:00Z")
    client.channel_sections_list(channel_id="UC_a")
    p = [c["params"] for c in transport.calls]
    assert p[0]["id"] == "UC_a,UC_b" and p[0]["part"] == "snippet,statistics"
    assert p[1]["forHandle"] == "@testhandle"
    assert p[2]["id"] == "v1,v2"
    assert p[3]["allThreadsRelatedToChannelId"] == "UC_a"
    assert p[4]["regionCode"] == "LK" and p[4]["type"] == "channel" and p[4]["publishedAfter"]
    assert transport.calls[5]["url"].endswith("/channelSections")


def test_missing_items_means_empty_page():
    client, _, _ = make(ok({"kind": "x"}))
    assert client.videos_list(part="id", id="v1").items == []


def test_real_transport_encodes_params_safely(monkeypatch):
    seen = {}

    class Resp:
        status, headers = 200, {}

        def read(self):
            return b'{"items": []}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(request, timeout):
        seen["url"], seen["timeout"] = request.full_url, timeout
        return Resp()

    monkeypatch.setattr(yc.urllib.request, "urlopen", fake_urlopen)
    YouTubeClient(api_key=KEY, timeout=5).search_list(q="a&b=c #x", type="channel")
    assert "q=a%26b%3Dc+%23x" in seen["url"] and seen["timeout"] == 5


# --- pagination ---------------------------------------------------------------------

def test_page_token_passed_and_returned():
    client, transport, _ = make(ok({"items": [], "nextPageToken": "P2", "prevPageToken": "P0"}))
    r = client.comment_threads_list(video_id="v1", page_token="P1", max_results=100)
    assert transport.calls[0]["params"]["pageToken"] == "P1"
    assert (r.next_page_token, r.prev_page_token) == ("P2", "P0")


@pytest.mark.parametrize("token", ["", "has space", "x" * 600, 123, "a&key=evil"])
def test_invalid_page_token(token):
    client, transport, _ = make(ok())
    with pytest.raises(yc.RequestValidationError):
        client.comment_threads_list(video_id="v1", page_token=token)
    assert transport.calls == []  # nothing sent


# --- parameter validation (nothing is sent) -----------------------------------------------

@pytest.mark.parametrize("call", [
    lambda c: c.channels_list(part="snippet"),                                 # no id / handle
    lambda c: c.channels_list(part="snippet", id="UC_a", for_handle="@x"),     # both
    lambda c: c.channels_list(part="", id="UC_a"),                             # empty part
    lambda c: c.channels_list(part="snippet,secrets", id="UC_a"),             # unknown part
    lambda c: c.channels_list(part="snippet", id=""),                          # empty id
    lambda c: c.channels_list(part="snippet", id=["UC_a", ""]),
    lambda c: c.channels_list(part="snippet", id=[f"UC_{i}" for i in range(51)]),  # > 50 ids
    lambda c: c.channels_list(part="snippet", id="bad id"),
    lambda c: c.channels_list(part="snippet", for_handle="@a b"),
    lambda c: c.videos_list(part="snippet", id=None),
    lambda c: c.comment_threads_list(),                                        # no target
    lambda c: c.comment_threads_list(video_id="v1", max_results=0),
    lambda c: c.comment_threads_list(video_id="v1", max_results=101),
    lambda c: c.comment_threads_list(video_id="v1", max_results=True),
    lambda c: c.comment_threads_list(video_id="v1", order="newest"),
    lambda c: c.comment_threads_list(video_id="v1,v2"),                        # one video only
    lambda c: c.search_list(),
    lambda c: c.search_list(q="x", max_results=51),
    lambda c: c.search_list(q="x", type="user"),
    lambda c: c.search_list(q="x", region_code="LKA"),
    lambda c: c.search_list(q="x", published_after="yesterday"),
    lambda c: c.channel_sections_list(channel_id="UC_a", part="statistics"),
])
def test_parameter_validation(call):
    client, transport, _ = make(ok())
    with pytest.raises(yc.RequestValidationError):
        call(client)
    assert transport.calls == []
    assert client.quota_used == 0


# --- HTTP errors --------------------------------------------------------------------

@pytest.mark.parametrize("status, reason, exc", [
    (400, "badRequest", yc.BadRequestError),
    (400, "keyInvalid", yc.InvalidAPIKeyError),
    (401, None, yc.UnauthorizedError),
    (403, "forbidden", yc.ForbiddenError),
    (403, "commentsDisabled", yc.ForbiddenError),
    (403, "quotaExceeded", yc.QuotaExceededError),
    (403, "accessNotConfigured", yc.InvalidAPIKeyError),
    (404, "videoNotFound", yc.NotFoundError),
])
def test_permanent_errors_not_retried(status, reason, exc):
    client, transport, sleeps = make(api_error(status, reason))
    with pytest.raises(exc) as err:
        client.videos_list(part="id", id="v1")
    assert err.value.status == status and err.value.reason == reason
    assert err.value.resource == "videos"
    assert len(transport.calls) == 1 and sleeps == []
    assert client.request_log[-1].succeeded is False


def test_api_key_not_valid_message_maps_to_invalid_key():
    client, _, _ = make(api_error(400, None, message="API key not valid. Please pass a valid API key."))
    with pytest.raises(yc.InvalidAPIKeyError):
        client.channels_list(part="id", id="UC_a")


def test_quota_error_explains_reset():
    client, _, _ = make(api_error(403, "quotaExceeded"))
    with pytest.raises(yc.QuotaExceededError, match="midnight Pacific"):
        client.search_list(q="x")


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_server_errors_retried_then_succeed(status):
    client, transport, sleeps = make(api_error(status), api_error(status), ok({"items": [{"id": "v1"}]}))
    r = client.videos_list(part="id", id="v1")
    assert r.items == [{"id": "v1"}]
    assert len(transport.calls) == 3
    assert len(sleeps) == 2 and 1 <= sleeps[0] <= 1.1 and 2 <= sleeps[1] <= 2.2  # exponential backoff
    assert client.request_log[-1].attempts == 3 and client.request_log[-1].succeeded


def test_retry_limit_reached():
    client, transport, sleeps = make(api_error(503), retries=2)
    with pytest.raises(yc.ServerError):
        client.videos_list(part="id", id="v1")
    assert len(transport.calls) == 3  # 1 attempt + 2 retries
    assert len(sleeps) == 2


def test_backoff_is_capped():
    client, _, sleeps = make(api_error(500), retries=5)
    with pytest.raises(yc.ServerError):
        client.videos_list(part="id", id="v1")
    assert max(sleeps) <= 8 * 1.1


def test_429_retried_honouring_retry_after():
    client, transport, sleeps = make(api_error(429, headers={"Retry-After": "5"}), ok())
    client.videos_list(part="id", id="v1")
    assert len(transport.calls) == 2
    assert 5 <= sleeps[0] <= 5.5


def test_rate_limit_reason_on_403_retried():
    client, transport, _ = make(api_error(403, "rateLimitExceeded"), ok())
    client.videos_list(part="id", id="v1")
    assert len(transport.calls) == 2


def test_no_retries_when_disabled():
    client, transport, sleeps = make(api_error(503), retries=0)
    with pytest.raises(yc.ServerError):
        client.videos_list(part="id", id="v1")
    assert len(transport.calls) == 1 and sleeps == []


# --- network failures ------------------------------------------------------------------

@pytest.mark.parametrize("failure", [socket.timeout("timed out"), TimeoutError(),
                                     urllib.error.URLError(socket.timeout("timed out"))])
def test_timeout_retried_then_raised(failure):
    client, transport, sleeps = make(failure, retries=2)
    with pytest.raises(yc.APITimeoutError, match="timed out"):
        client.channels_list(part="id", id="UC_a")
    assert len(transport.calls) == 3
    assert client.quota_used == 0  # never reached the API


@pytest.mark.parametrize("failure", [urllib.error.URLError("Name or service not known"),
                                     ConnectionResetError("reset"), OSError("network down")])
def test_connection_failure(failure):
    client, transport, _ = make(failure, ok({"items": [{"id": "x"}]}))
    assert client.channels_list(part="id", id="UC_a").items == [{"id": "x"}]  # recovered on retry
    assert len(transport.calls) == 2

    client2, _, _ = make(failure, retries=0)
    with pytest.raises(yc.NetworkError, match="connection failed"):
        client2.channels_list(part="id", id="UC_a")


# --- malformed responses -------------------------------------------------------------

@pytest.mark.parametrize("body", [b"<html>not json</html>", b"", b"[1, 2]", b'{"items": "nope"}', b"\xff\xfe"])
def test_malformed_response(body):
    client, transport, _ = make(HttpResult(200, {}, body))
    with pytest.raises(yc.MalformedResponseError):
        client.videos_list(part="id", id="v1")
    assert len(transport.calls) == 1  # not retried


def test_error_with_non_json_body():
    client, _, _ = make(HttpResult(502, {}, b"<html>Bad Gateway</html>"), retries=0)
    with pytest.raises(yc.ServerError) as err:
        client.videos_list(part="id", id="v1")
    assert err.value.status == 502 and err.value.reason is None


# --- quota awareness -------------------------------------------------------------------

def test_quota_accounting_and_request_log():
    client, _, _ = make(ok(), ok(), api_error(404, "videoNotFound"))
    client.search_list(q="x")                     # 100
    client.channels_list(part="id", id="UC_a")    # 1
    with pytest.raises(yc.NotFoundError):
        client.videos_list(part="id", id="v1")    # 1 (answered by the API, still counts)
    assert client.quota_used == 102
    log = client.request_log
    assert [(r.resource, r.succeeded, r.quota_cost) for r in log] == [
        ("search", True, 100), ("channels", True, 1), ("videos", False, 1)]
    assert log[2].http_status == 404 and log[2].error == "videoNotFound"
    assert all(r.method == "list" and r.at.endswith("Z") for r in log)


def test_cost_table_matches_api():
    assert yc.COST == {"channels": 1, "videos": 1, "commentThreads": 1, "channelSections": 1, "search": 100}


# --- the key never leaks ---------------------------------------------------------------

def test_key_not_in_errors_logs_or_records(caplog):
    caplog.set_level(logging.DEBUG)
    leaky = api_error(400, "badRequest",
                      message=f"Bad request for https://x/youtube/v3/videos?id=v1&key={KEY}&alt=json key {KEY}")
    client, _, _ = make(api_error(503), leaky)
    with pytest.raises(yc.BadRequestError) as err:
        client.videos_list(part="id", id="v1")
    exc = err.value
    everything = " ".join([str(exc), repr(exc), caplog.text, repr(client.request_log), repr(client)])
    assert KEY not in everything
    assert exc.__cause__ is None and exc.__context__ is None or KEY not in str(exc.__context__)


def test_key_not_in_network_error():
    client, _, _ = make(urllib.error.URLError(f"failed for ...&key={KEY}"), retries=0)
    with pytest.raises(yc.NetworkError) as err:
        client.videos_list(part="id", id="v1")
    assert KEY not in str(err.value)
    assert err.value.__cause__ is None and err.value.__suppress_context__


def test_errors_are_structured_for_collectors():
    for cls in (yc.QuotaExceededError, yc.RateLimitError, yc.NotFoundError, yc.NetworkError,
                yc.MalformedResponseError, yc.MissingAPIKeyError):
        assert issubclass(cls, yc.YouTubeAPIError)
    assert yc.RateLimitError.retryable and yc.ServerError.retryable and yc.NetworkError.retryable
    assert not yc.QuotaExceededError.retryable and not yc.BadRequestError.retryable
    assert issubclass(yc.RequestValidationError, ValueError)
