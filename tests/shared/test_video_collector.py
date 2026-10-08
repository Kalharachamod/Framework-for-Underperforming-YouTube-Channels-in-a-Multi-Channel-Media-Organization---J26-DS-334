"""Tests for the video collector.

No real YouTube API (mocked HTTP transport) and no real Supabase (an in-memory
store, or the throwaway local PostgreSQL from conftest). All channels and
videos are TEST DATA with synthetic ids.
"""

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from shared.data_collection import video_collector as vc
from shared.data_collection.youtube_client import HttpResult, RetryPolicy, YouTubeClient
from shared.database import repository as repo
from shared.schemas import Channel

NOW = datetime(2026, 10, 8, 6, 0, tzinfo=timezone.utc)


def video_item(vid, cid, published="2026-10-01T09:00:00Z", views="100", **kw):
    stats = {"viewCount": views, "likeCount": kw.get("likes", "10"), "commentCount": kw.get("comments", "2")}
    for k in kw.get("drop", []):
        stats.pop(k)
    return {"kind": "youtube#video", "id": vid,
            "snippet": {"channelId": cid, "title": kw.get("title", f"Test {vid}"), "description": "Synthetic.",
                        "publishedAt": published, "tags": kw.get("tags", ["test"])},
            "statistics": stats, "contentDetails": {"duration": kw.get("duration", "PT4M13S")}}


class FakeAPI:
    """Mocked YouTube API: channels (uploads playlists), paginated playlistItems, videos."""

    def __init__(self, channels, *, page_size=50, fail=None, hidden=(), bad_tokens=False):
        # channels: {channel_id: [video items newest first]}
        self.channels = channels
        self.page_size = page_size
        self.fail = dict(fail or {})  # resource -> list of HttpResult/exceptions to return first
        self.hidden = set(hidden)      # video ids listed in the playlist but not returned by videos.list
        self.bad_tokens = bad_tokens
        self.calls = []

    def __call__(self, url, params, timeout):
        resource = url.rsplit("/", 1)[-1]
        self.calls.append((resource, dict(params)))
        if self.fail.get(resource):
            f = self.fail[resource].pop(0)
            if isinstance(f, BaseException):
                raise f
            return f
        if resource == "channels":
            items = [{"id": c, "contentDetails": {"relatedPlaylists": {"uploads": "UU" + c[2:]}}}
                     for c in params["id"].split(",") if c in self.channels]
            return ok({"items": items})
        if resource == "playlistItems":
            cid = "UC" + params["playlistId"][2:]
            vids = self.channels[cid]
            start = int(params.get("pageToken", "T0")[1:]) if not self.bad_tokens else 0
            size = min(self.page_size, int(params.get("maxResults", 50)))
            page = vids[start:start + size]
            body = {"items": [{"contentDetails": {"videoId": v["id"], "videoPublishedAt": v["snippet"]["publishedAt"]}}
                              for v in page], "pageInfo": {"totalResults": len(vids)}}
            if start + size < len(vids):
                body["nextPageToken"] = "T0" if self.bad_tokens else f"T{start + size}"
            return ok(body)
        if resource == "videos":
            all_videos = {v["id"]: v for vs in self.channels.values() for v in vs}
            ids = params["id"].split(",")
            return ok({"items": [all_videos[i] for i in ids if i in all_videos and i not in self.hidden]})
        raise AssertionError(f"unexpected resource {resource}")

    def count(self, resource):
        return sum(1 for r, _ in self.calls if r == resource)


def ok(body):
    return HttpResult(200, {}, json.dumps(body).encode())


def error(status, reason=None):
    return HttpResult(status, {}, json.dumps({"error": {"code": status, "message": "x",
                                                         "errors": [{"reason": reason}] if reason else []}}).encode())


def client(api, retries=0):
    return YouTubeClient(api_key="TEST_KEY_not_real", transport=api, sleep=lambda s: None,
                         retry=RetryPolicy(max_retries=retries))


def videos_for(cid, n, start_day=30):
    return [video_item(f"{cid[3:]}_v{i:03d}", cid,
                       published=(datetime(2026, 9, start_day, tzinfo=timezone.utc) - timedelta(days=i))
                       .isoformat().replace("+00:00", "Z")) for i in range(n)]


class MemoryStore:
    def __init__(self):
        self.rows, self.calls = {}, 0

    def __call__(self, videos):
        self.calls += 1
        ins, upd, chg = [], [], []
        for v in videos:
            old = self.rows.get(v.video_id)
            (upd if old else ins).append(v.video_id)
            if old and old.model_dump(exclude={"collected_at"}) != v.model_dump(exclude={"collected_at"}):
                chg.append(v.video_id)
            self.rows[v.video_id] = v
        return repo.WriteSummary("videos", len(videos), len(ins), len(upd), 0, tuple(ins), tuple(upd),
                                 tuple(chg), tuple(i for i in upd if i not in chg))


def known(*ids):
    return lambda requested: set(ids) & set(requested)


A, B = "UC_test_a", "UC_test_b"


# --- single / multiple channels ---------------------------------------------------------

def test_single_channel():
    api, store = FakeAPI({A: videos_for(A, 3)}), MemoryStore()
    r = vc.collect_videos([A], client(api), store, known_channels=known(A), clock=lambda: NOW)
    assert r.ok and r.channels_processed == [A]
    assert r.videos_discovered == 3 and len(r.videos_inserted) == 3
    v = store.rows["test_a_v000"]
    assert v.channel_id == A and v.title == "Test test_a_v000" and v.tags == ["test"]
    assert v.view_count == 100 and v.like_count == 10 and v.comment_count == 2
    assert v.duration_seconds == 253
    assert v.collected_at == NOW and v.published_at < v.collected_at


def test_multiple_channels_one_channels_list_call():
    api, store = FakeAPI({A: videos_for(A, 2), B: videos_for(B, 4)}), MemoryStore()
    r = vc.collect_videos([A, B], client(api), store, known_channels=known(A, B))
    assert r.channels_processed == [A, B] and len(store.rows) == 6
    assert api.count("channels") == 1  # uploads playlists of both channels in one request
    assert api.count("search") == 0


# --- pagination ----------------------------------------------------------------------

def test_one_page():
    api = FakeAPI({A: videos_for(A, 5)})
    r = vc.collect_videos([A], client(api), MemoryStore(), known_channels=known(A))
    assert api.count("playlistItems") == 1 and r.videos_discovered == 5


def test_multiple_pages_follow_tokens_until_final_page():
    api = FakeAPI({A: videos_for(A, 23)}, page_size=10)
    r = vc.collect_videos([A], client(api), MemoryStore(), known_channels=known(A), max_videos_per_channel=100)
    tokens = [p.get("pageToken") for res, p in api.calls if res == "playlistItems"]
    assert tokens == [None, "T10", "T20"]  # third page has no nextPageToken -> stop
    assert r.videos_discovered == 23


def test_limit_stops_pagination_early():
    api = FakeAPI({A: videos_for(A, 120)})
    r = vc.collect_videos([A], client(api), MemoryStore(), known_channels=known(A), max_videos_per_channel=60)
    assert r.videos_discovered == 60
    assert [p["maxResults"] for res, p in api.calls if res == "playlistItems"] == ["50", "10"]


def test_since_stops_at_older_videos():
    api = FakeAPI({A: videos_for(A, 30)}, page_size=10)  # published 09-30, 09-29, ...
    r = vc.collect_videos([A], client(api), MemoryStore(), known_channels=known(A),
                          max_videos_per_channel=100, published_since=date(2026, 9, 25))
    assert r.videos_discovered == 6  # 09-30 .. 09-25
    assert api.count("playlistItems") == 1  # older videos on the first page -> no further pages


def test_empty_playlist_and_missing_playlist():
    api = FakeAPI({A: [], B: videos_for(B, 1)}, fail={"playlistItems": [error(404, "playlistNotFound")]})
    r = vc.collect_videos([A, B], client(api), MemoryStore(), known_channels=known(A, B))
    assert r.channels_processed == [A, B] and r.videos_discovered == 1 and r.ok


def test_repeated_page_token_does_not_loop():
    api = FakeAPI({A: videos_for(A, 30)}, page_size=10, bad_tokens=True)
    r = vc.collect_videos([A], client(api), MemoryStore(), known_channels=known(A), max_videos_per_channel=100)
    assert [f.reason for f in r.channel_failures] == ["pagination_error"]
    assert api.count("playlistItems") <= 3


def test_malformed_playlist_entries_skipped():
    api = FakeAPI({A: videos_for(A, 2)})
    original = api.__call__

    def transport(url, params, timeout):
        res = original(url, params, timeout)
        if url.endswith("/playlistItems"):
            body = json.loads(res.body)
            body["items"].append({"contentDetails": {}})  # no videoId
            body["items"].append("garbage")
            return ok(body)
        return res

    r = vc.collect_videos([A], client(transport), MemoryStore(), known_channels=known(A))
    assert r.videos_discovered == 2 and r.ok


# --- batching ------------------------------------------------------------------------

def test_metadata_fetched_in_batches_of_50():
    api = FakeAPI({A: videos_for(A, 120)})
    c = client(api)
    r = vc.collect_videos([A], c, MemoryStore(), known_channels=known(A), max_videos_per_channel=120)
    sizes = [len(p["id"].split(",")) for res, p in api.calls if res == "videos"]
    assert sizes == [50, 50, 20]  # not one request per video
    assert r.quota_used == 1 + 3 + 3  # channels.list + 3 playlist pages + 3 videos.list
    assert api.calls[-1][1]["part"] == "snippet,statistics,contentDetails"


# --- upserts --------------------------------------------------------------------------

def test_new_then_existing_video():
    store = MemoryStore()
    vc.collect_videos([A], client(FakeAPI({A: videos_for(A, 2)})), store, known_channels=known(A))
    updated = videos_for(A, 2)
    updated[0]["statistics"]["viewCount"] = "999"
    r = vc.collect_videos([A], client(FakeAPI({A: updated})), store, known_channels=known(A),
                          clock=lambda: NOW + timedelta(hours=1))
    assert r.videos_inserted == [] and sorted(r.videos_updated) == ["test_a_v000", "test_a_v001"]
    assert r.videos_changed == ["test_a_v000"] and r.videos_refreshed == ["test_a_v001"]
    assert len(store.rows) == 2 and store.rows["test_a_v000"].view_count == 999


def test_hidden_likes_and_disabled_comments_are_none():
    vids = [video_item("test_v_h", A, drop=["likeCount", "commentCount"])]
    store = MemoryStore()
    vc.collect_videos([A], client(FakeAPI({A: vids})), store, known_channels=known(A))
    v = store.rows["test_v_h"]
    assert v.like_count is None and v.comment_count is None


# --- validation and data problems ---------------------------------------------------------

def test_invalid_video_not_persisted():
    vids = videos_for(A, 1) + [video_item("test_v_bad", A, views="-1"),
                               video_item("test_v_notitle", A, title=None)]
    store = MemoryStore()
    r = vc.collect_videos([A], client(FakeAPI({A: vids})), store, known_channels=known(A))
    reasons = {f.video_id: (f.reason, f.message) for f in r.video_failures}
    assert reasons["test_v_bad"][0] == "validation_error" and "view_count" in reasons["test_v_bad"][1]
    assert reasons["test_v_notitle"][0] == "validation_error" and "title" in reasons["test_v_notitle"][1]
    assert set(store.rows) == {"test_a_v000"}


def test_unavailable_video_metadata():
    api = FakeAPI({A: videos_for(A, 2)}, hidden={"test_a_v001"})
    r = vc.collect_videos([A], client(api), MemoryStore(), known_channels=known(A))
    assert [(f.video_id, f.reason) for f in r.video_failures] == [("test_a_v001", "unavailable")]


def test_video_of_other_channel_rejected():
    vids = [video_item("test_v_foreign", B)]  # listed in A's uploads but belongs to B
    r = vc.collect_videos([A], client(FakeAPI({A: vids})), MemoryStore(), known_channels=known(A))
    assert r.video_failures[0].reason == "channel_mismatch"


@pytest.mark.parametrize("duration, seconds", [("PT4M13S", 253), ("PT1H", 3600), ("P1DT2H3M4S", 93784),
                                               ("P0D", 0), ("PT0S", 0), (None, None), ("garbage", None), ("PT", None)])
def test_parse_duration(duration, seconds):
    assert vc.parse_duration(duration) == seconds


# --- channels -------------------------------------------------------------------------

def test_channel_not_in_database_not_collected():
    api = FakeAPI({A: videos_for(A, 1), B: videos_for(B, 1)})
    r = vc.collect_videos([A, B], client(api), MemoryStore(), known_channels=known(A))
    assert [(f.channel_id, f.reason) for f in r.channel_failures] == [(B, "channel_not_stored")]
    assert r.channels_processed == [A]
    assert B not in api.calls[0][1]["id"]  # no quota spent on B


def test_invalid_and_unknown_channels():
    api = FakeAPI({A: videos_for(A, 1)})
    r = vc.collect_videos([A, "bad id", "UC_test_gone"], client(api), MemoryStore(),
                          known_channels=lambda ids: set(ids))
    reasons = {f.channel_id: f.reason for f in r.channel_failures}
    assert reasons == {"bad id": "invalid_id", "UC_test_gone": "not_found"}
    assert r.channels_processed == [A]


# --- API errors -------------------------------------------------------------------------

@pytest.mark.parametrize("response, reason, stops", [
    (error(403, "quotaExceeded"), "quota_exceeded", True),
    (error(400, "keyInvalid"), "auth_error", True),
    (error(403, "forbidden"), "api_error", False),
    (error(404, "videoNotFound"), "api_error", False),
    (error(429), "api_error", False),
    (error(500), "api_error", False),
    (TimeoutError(), "api_error", False),
    (OSError("network down"), "api_error", False),
])
def test_api_errors_on_video_metadata(response, reason, stops):
    api = FakeAPI({A: videos_for(A, 2), B: videos_for(B, 2)}, fail={"videos": [response]})
    store = MemoryStore()
    r = vc.collect_videos([A, B], client(api), store, known_channels=known(A, B))
    failures = r.channel_failures if stops else r.video_failures
    assert {f.reason for f in failures} == {reason}
    if stops:
        assert r.channels_skipped == [B] and store.calls == 0
    else:
        assert set(store.rows) == {"test_b_v000", "test_b_v001"}  # B unaffected by A's failure


def test_api_error_on_playlist_isolated_to_channel():
    api = FakeAPI({A: videos_for(A, 2), B: videos_for(B, 2)}, fail={"playlistItems": [error(500)]})
    r = vc.collect_videos([A, B], client(api), MemoryStore(), known_channels=known(A, B))
    assert [(f.channel_id, f.reason) for f in r.channel_failures] == [(A, "api_error")]
    assert r.channels_processed == [B]


def test_quota_exhausted_on_channels_lookup():
    api = FakeAPI({A: videos_for(A, 1)}, fail={"channels": [error(403, "quotaExceeded")]})
    r = vc.collect_videos([A], client(api), MemoryStore(), known_channels=known(A))
    assert r.channel_failures[0].reason == "quota_exceeded" and api.count("playlistItems") == 0


def test_transient_error_recovered_by_client():
    api = FakeAPI({A: videos_for(A, 1)}, fail={"videos": [error(503)]})
    r = vc.collect_videos([A], client(api, retries=2), MemoryStore(), known_channels=known(A))
    assert r.ok and len(r.videos_collected) == 1


# --- database failures ------------------------------------------------------------------

def test_database_write_failure_reported():
    def broken(videos):
        raise repo.ReferentialIntegrityError("db down (test)")
    r = vc.collect_videos([A], client(FakeAPI({A: videos_for(A, 2)})), broken, known_channels=known(A))
    assert {f.reason for f in r.video_failures} == {"storage_error"} and r.videos_collected == []


def test_database_unavailable_for_channel_check():
    def down(ids):
        raise RuntimeError("connection lost (test)")
    api = FakeAPI({A: videos_for(A, 1)})
    r = vc.collect_videos([A], client(api), MemoryStore(), known_channels=down)
    assert r.channel_failures[0].reason == "storage_error" and api.calls == []


# --- configuration / misc ----------------------------------------------------------------

def test_empty_channel_list():
    with pytest.raises(ValueError, match="no channel ids"):
        vc.collect_videos([], client(FakeAPI({})), MemoryStore())


@pytest.mark.parametrize("bad", [0, -1, True, 2.5])
def test_invalid_limit(bad):
    with pytest.raises(ValueError):
        vc.collect_videos([A], client(FakeAPI({A: []})), MemoryStore(), max_videos_per_channel=bad)


def test_dry_run_and_summary():
    r = vc.collect_videos([A], client(FakeAPI({A: videos_for(A, 2)})), None, known_channels=known(A))
    assert len(r.videos_collected) == 2 and r.videos_inserted == [] and "dry run" in r.summary()
    assert "TEST_KEY_not_real" not in r.summary() + repr(r)


# --- with the real (throwaway) PostgreSQL ------------------------------------------------

def test_collect_into_database_twice(db):
    repo.upsert_channels(db, [Channel(channel_id=A, channel_name="Test A", collected_at=NOW)])
    db.commit()
    api = FakeAPI({A: videos_for(A, 3), B: videos_for(B, 1)})
    first = vc.collect_videos([A, B], client(api), vc.supabase_store(db),
                              known_channels=vc.supabase_known_channels(db), clock=lambda: NOW)
    second = vc.collect_videos([A, B], client(api), vc.supabase_store(db),
                               known_channels=vc.supabase_known_channels(db), clock=lambda: NOW + timedelta(hours=1))
    assert len(first.videos_inserted) == 3 and second.videos_inserted == []
    assert len(second.videos_refreshed) == 3
    assert [f.reason for f in first.channel_failures] == ["channel_not_stored"]  # B: no orphan videos
    assert repo.count_rows(db, "videos") == 3
    v = repo.get_video(db, "test_a_v000")
    assert v.duration_seconds == 253 and v.collected_at == NOW + timedelta(hours=1)
