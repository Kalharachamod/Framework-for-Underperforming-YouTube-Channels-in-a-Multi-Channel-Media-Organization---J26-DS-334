"""Tests for the comment collector.

No real YouTube API (mocked HTTP transport) and no real Supabase (an in-memory
store, or the throwaway local PostgreSQL from conftest). All comments, ids and
commenter ids are TEST DATA. Raw commenter ids are synthetic and asserted never
to appear in stored data, results or logs (they are not printed by any test).
"""

import json
import logging
from datetime import datetime, timedelta, timezone

import pytest

from shared.data_collection import comment_collector as cc
from shared.data_collection.comment_collector import VideoRef
from shared.data_collection.youtube_client import HttpResult, RetryPolicy, YouTubeClient
from shared.database import repository as repo
from shared.schemas import Channel, Video
from shared.utils import privacy

NOW = datetime(2026, 10, 8, 9, 0, tzinfo=timezone.utc)
SALT = b"test-salt-" + b"0" * 54
RAW = {n: f"UC_raw_author_{n:02d}_xx" for n in range(10)}  # TEST raw commenter ids


def comment_res(cid, vid, author=1, text="Synthetic comment.", published="2026-10-05T10:00:00Z", likes=1, **kw):
    snippet = {"videoId": vid, "textDisplay": text, "publishedAt": published, "updatedAt": published,
               "likeCount": likes, "authorDisplayName": "Test Person", "authorProfileImageUrl": "http://x/img"}
    if author is not None:
        snippet["authorChannelId"] = {"value": RAW[author]}
    snippet.update(kw)
    return {"kind": "youtube#comment", "id": cid, "snippet": snippet}


def thread(tid, vid, *, replies=(), total=None, **kw):
    t = {"kind": "youtube#commentThread", "id": tid,
         "snippet": {"videoId": vid, "topLevelComment": comment_res(tid, vid, **kw),
                     "totalReplyCount": len(replies) if total is None else total}}
    if replies:
        t["replies"] = {"comments": list(replies)}
    return t


class FakeAPI:
    """Mocked commentThreads.list / comments.list with pagination and failures."""

    def __init__(self, threads, *, page_size=100, extra_replies=None, fail=None, bad_tokens=False):
        self.threads = threads                    # video_id -> [threads newest first]
        self.extra_replies = extra_replies or {}  # parent id -> full reply list
        self.page_size = page_size
        self.fail = {k: list(v) for k, v in (fail or {}).items()}  # (resource, video_or_parent) -> responses
        self.bad_tokens = bad_tokens
        self.calls = []

    def __call__(self, url, params, timeout):
        resource = url.rsplit("/", 1)[-1]
        target = params.get("videoId") or params.get("parentId")
        self.calls.append((resource, dict(params)))
        queue = self.fail.get((resource, target))
        if queue:
            f = queue.pop(0)
            if isinstance(f, BaseException):
                raise f
            return f
        items = self.threads.get(target, []) if resource == "commentThreads" else self.extra_replies.get(target, [])
        start = 0 if self.bad_tokens else int(params.get("pageToken", "T0")[1:])
        size = min(self.page_size, int(params.get("maxResults", 100)))
        body = {"items": items[start:start + size]}
        if start + size < len(items):
            body["nextPageToken"] = "T0" if self.bad_tokens else f"T{start + size}"
        return HttpResult(200, {}, json.dumps(body).encode())

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


class MemoryStore:
    def __init__(self):
        self.rows, self.calls = {}, 0

    def __call__(self, comments):
        self.calls += 1
        ins, upd, chg = [], [], []
        for c in comments:
            old = self.rows.get(c.comment_id)
            (upd if old else ins).append(c.comment_id)
            if old and old.model_dump(exclude={"collected_at"}) != c.model_dump(exclude={"collected_at"}):
                chg.append(c.comment_id)
            self.rows[c.comment_id] = c
        return repo.WriteSummary("comments", len(comments), len(ins), len(upd), 0, tuple(ins), tuple(upd),
                                 tuple(chg), tuple(i for i in upd if i not in chg))


V1, V2, CH = "test_vid_1", "test_vid_2", "UC_test_ch"


def refs(*vids, count=5):
    return [VideoRef(v, CH, count) for v in vids]


def run(api, store=None, videos=None, **kw):
    return cc.collect_comments(videos or refs(V1), client(api), store if store is not None else MemoryStore(),
                               salt=SALT, clock=lambda: NOW, **kw)


def everything_text(result, store):
    return " ".join([result.summary(), repr(result), repr(list(store.rows.values())),
                     json.dumps([c.model_dump(mode="json") for c in store.rows.values()])])


# --- basic collection ---------------------------------------------------------------------

def test_basic_collection():
    api, store = FakeAPI({V1: [thread("c1", V1), thread("c2", V1, author=2)]}), MemoryStore()
    r = run(api, store)
    assert r.ok and r.videos_processed == [V1]
    assert sorted(r.comments_inserted) == ["c1", "c2"] and r.top_level_comments == 2 and r.replies == 0
    c = store.rows["c1"]
    assert c.video_id == V1 and c.channel_id == CH and c.comment_text == "Synthetic comment."
    assert c.parent_comment_id is None and c.like_count == 1
    assert c.published_at == datetime(2026, 10, 5, 10, tzinfo=timezone.utc)
    assert c.collected_at == NOW and c.edited_at == c.published_at
    params = api.calls[0][1]
    assert (params["part"], params["order"], params["textFormat"], params["maxResults"]) == \
        ("snippet,replies", "time", "plainText", "100")


def test_multiple_videos_independent():
    api = FakeAPI({V1: [thread("c1", V1)], V2: [thread("c2", V2)]}, fail={("commentThreads", V1): [error(500)]})
    store = MemoryStore()
    r = run(api, store, refs(V1, V2))
    assert [f.reason for f in r.video_failures] == ["api_error"] and r.videos_processed == [V2]
    assert set(store.rows) == {"c2"}


def test_videos_without_comments_cost_no_quota():
    api = FakeAPI({V1: [thread("c1", V1)]})
    r = run(api, videos=[VideoRef(V1, CH, 0), VideoRef(V2, CH, 3)])
    assert r.videos_skipped == [V1] and r.quota_used == 1  # only V2 requested
    assert all(p.get("videoId") != V1 for _, p in api.calls)


# --- pagination --------------------------------------------------------------------------

def test_multiple_pages_and_final_page():
    threads = [thread(f"c{i:03d}", V1) for i in range(23)]
    api = FakeAPI({V1: threads}, page_size=10)
    r = run(api, max_threads_per_video=100)
    tokens = [p.get("pageToken") for res, p in api.calls if res == "commentThreads"]
    assert tokens == [None, "T10", "T20"] and len(r.comments_collected) == 23


def test_thread_limit_stops_pagination():
    api = FakeAPI({V1: [thread(f"c{i:03d}", V1) for i in range(250)]})
    r = run(api, max_threads_per_video=150)
    assert [p["maxResults"] for res, p in api.calls if res == "commentThreads"] == ["100", "50"]
    assert r.top_level_comments == 150


def test_empty_response():
    r = run(FakeAPI({V1: []}))
    assert r.videos_processed == [V1] and r.comments_discovered == 0 and r.ok


def test_repeated_token_does_not_loop():
    api = FakeAPI({V1: [thread(f"c{i:03d}", V1) for i in range(30)]}, page_size=10, bad_tokens=True)
    r = run(api)
    assert [f.reason for f in r.video_failures] == ["pagination_error"]
    assert api.count("commentThreads") <= 3


def test_incremental_stops_at_known_threads():
    threads = [thread(f"c{i:03d}", V1, published=(NOW - timedelta(days=i + 1)).isoformat().replace("+00:00", "Z"))
               for i in range(30)]
    api = FakeAPI({V1: threads}, page_size=10)
    known = VideoRef(V1, CH, 30, latest_stored_comment=NOW - timedelta(days=5))
    r = run(api, videos=[known], incremental=True)
    assert api.count("commentThreads") == 1  # stopped after the page reaching stored threads


# --- replies ------------------------------------------------------------------------------

def test_embedded_replies_linked_to_parent():
    t = thread("c1", V1, replies=[comment_res("c1.r1", V1, author=3), comment_res("c1.r2", V1, author=4)])
    api, store = FakeAPI({V1: [t]}), MemoryStore()
    r = run(api, store)
    assert r.top_level_comments == 1 and r.replies == 2
    assert store.rows["c1.r1"].parent_comment_id == "c1" and store.rows["c1"].parent_comment_id is None
    assert api.count("comments") == 0  # all replies embedded: no extra calls


def test_all_replies_fetched_when_thread_incomplete_without_duplicates():
    embedded = [comment_res(f"c1.r{i}", V1) for i in range(5)]
    full = [comment_res(f"c1.r{i}", V1) for i in range(12)]
    api = FakeAPI({V1: [thread("c1", V1, replies=embedded, total=12)]}, extra_replies={"c1": full})
    store = MemoryStore()
    r = run(api, store)
    assert api.count("comments") == 1
    assert len([c for c in store.rows.values() if c.parent_comment_id == "c1"]) == 12
    assert len(r.comments_collected) == 13 and len(set(r.comments_collected)) == 13


def test_no_extra_replies_option_saves_quota():
    embedded = [comment_res(f"c1.r{i}", V1) for i in range(5)]
    api = FakeAPI({V1: [thread("c1", V1, replies=embedded, total=40)]})
    r = run(api, fetch_all_replies=False)
    assert api.count("comments") == 0 and r.replies == 5


def test_replies_of_invalid_parent_not_stored():
    t = thread("c1", V1, replies=[comment_res("c1.r1", V1)], publishedAt="not-a-date")
    store = MemoryStore()
    r = run(FakeAPI({V1: [t]}), store)
    assert store.rows == {} and r.comment_failures[0].reason == "validation_error"


# --- updates / duplicates ------------------------------------------------------------------

def test_repeat_run_updates_not_duplicates():
    store = MemoryStore()
    run(FakeAPI({V1: [thread("c1", V1, likes=1), thread("c2", V1)]}), store)
    r = cc.collect_comments(refs(V1), client(FakeAPI({V1: [thread("c1", V1, likes=9), thread("c2", V1)]})), store,
                            salt=SALT, clock=lambda: NOW + timedelta(hours=1))
    assert r.comments_inserted == [] and r.comments_changed == ["c1"] and r.comments_refreshed == ["c2"]
    assert len(store.rows) == 2 and store.rows["c1"].like_count == 9


def test_edited_comment_text_updates():
    store = MemoryStore()
    run(FakeAPI({V1: [thread("c1", V1)]}), store)
    edited = thread("c1", V1, text="Edited synthetic.", updatedAt="2026-10-07T00:00:00Z")
    cc.collect_comments(refs(V1), client(FakeAPI({V1: [edited]})), store, salt=SALT,
                        clock=lambda: NOW + timedelta(hours=1))
    c = store.rows["c1"]
    assert c.comment_text == "Edited synthetic." and c.edited_at > c.published_at


# --- privacy -----------------------------------------------------------------------------

def test_commenter_ids_pseudonymized_deterministically():
    t1 = thread("c1", V1, author=1)
    t2 = thread("c2", V2, author=1)   # same commenter, other video
    t3 = thread("c3", V1, author=2)   # different commenter
    store = MemoryStore()
    run(FakeAPI({V1: [t1, t3], V2: [t2]}), store, refs(V1, V2))
    a1, a2, a3 = (store.rows[c].author_channel_id for c in ("c1", "c2", "c3"))
    assert privacy.is_pseudonymized(a1) and a1 == a2 and a1 != a3
    assert a1 == privacy.pseudonymize_id(RAW[1], SALT)  # same id + same secret -> same pseudonym


def test_raw_ids_and_names_never_stored_or_returned(caplog):
    caplog.set_level(logging.DEBUG)
    t = thread("c1", V1, author=1, replies=[comment_res("c1.r1", V1, author=2)])
    store = MemoryStore()
    r = run(FakeAPI({V1: [t]}), store)
    text = everything_text(r, store) + caplog.text
    for raw in (RAW[1], RAW[2], "Test Person", "http://x/img"):
        assert raw not in text


def test_missing_author_stays_none():
    store = MemoryStore()
    run(FakeAPI({V1: [thread("c1", V1, author=None)]}), store)
    assert store.rows["c1"].author_channel_id is None


def test_missing_secret_fails_before_any_api_call(monkeypatch):
    monkeypatch.delenv("COMMENTER_HASH_SALT", raising=False)
    api = FakeAPI({V1: [thread("c1", V1)]})
    with pytest.raises(privacy.PrivacyConfigError):
        cc.collect_comments(refs(V1), client(api), MemoryStore())
    assert api.calls == []


def test_different_secret_gives_different_pseudonyms():
    s1, s2 = MemoryStore(), MemoryStore()
    run(FakeAPI({V1: [thread("c1", V1)]}), s1)
    cc.collect_comments(refs(V1), client(FakeAPI({V1: [thread("c1", V1)]})), s2, salt=b"other-" + b"1" * 40)
    assert s1.rows["c1"].author_channel_id != s2.rows["c1"].author_channel_id


# --- disabled comments and API errors -------------------------------------------------------

def test_comments_disabled_is_expected_not_error():
    api = FakeAPI({V2: [thread("c2", V2)]}, fail={("commentThreads", V1): [error(403, "commentsDisabled")]})
    r = run(api, videos=refs(V1, V2))
    assert r.videos_with_comments_disabled == [V1] and r.video_failures == [] and r.ok
    assert r.videos_processed == [V2]


@pytest.mark.parametrize("response, reason, stops", [
    (error(400, "badRequest"), "api_error", False),
    (error(400, "keyInvalid"), "auth_error", True),
    (error(401), "auth_error", True),
    (error(403, "forbidden"), "api_error", False),
    (error(403, "quotaExceeded"), "quota_exceeded", True),
    (error(404, "videoNotFound"), "video_unavailable", False),
    (error(429), "api_error", False),
    (error(500), "api_error", False),
    (TimeoutError(), "api_error", False),
    (OSError("network down"), "api_error", False),
])
def test_api_errors(response, reason, stops):
    api = FakeAPI({V2: [thread("c2", V2)]}, fail={("commentThreads", V1): [response]})
    store = MemoryStore()
    r = run(api, store, refs(V1, V2))
    assert [(f.video_id, f.reason) for f in r.video_failures] == [(V1, reason)]
    if stops:
        assert r.videos_skipped == [V2] and store.rows == {}
    else:
        assert set(store.rows) == {"c2"}


def test_reply_fetch_failure_keeps_embedded_replies():
    embedded = [comment_res("c1.r0", V1)]
    api = FakeAPI({V1: [thread("c1", V1, replies=embedded, total=9)]}, fail={("comments", "c1"): [error(500)]})
    store = MemoryStore()
    r = run(api, store)
    assert set(store.rows) == {"c1", "c1.r0"} and r.video_failures[0].reason == "replies_api_error"


def test_malformed_threads_skipped():
    items = [thread("c1", V1), {"snippet": {}}, "garbage", {"snippet": {"topLevelComment": {"id": "bad id!"}}}]
    r = run(FakeAPI({V1: items}))
    assert r.comments_skipped == 3 and r.comments_collected == ["c1"]


def test_malformed_response():
    api = FakeAPI({}, fail={("commentThreads", V1): [HttpResult(200, {}, b"<html>")]})
    r = run(api)
    assert r.video_failures[0].reason == "api_error"


# --- validation / database ------------------------------------------------------------------

def test_invalid_comments_not_persisted():
    items = [thread("c1", V1), thread("c2", V1, likes=-3), thread("c3", V1, textDisplay=None)]
    store = MemoryStore()
    r = run(FakeAPI({V1: items}), store)
    assert set(store.rows) == {"c1"}
    assert {f.comment_id for f in r.validation_failures} == {"c2", "c3"}


def test_comment_for_other_video_rejected():
    store = MemoryStore()
    r = run(FakeAPI({V1: [thread("c1", V1, videoId=V2)]}), store)
    assert store.rows == {} and r.comment_failures[0].reason == "video_mismatch"


def test_database_failure_reported():
    def broken(comments):
        raise repo.ReferentialIntegrityError("db down (test)")
    r = run(FakeAPI({V1: [thread("c1", V1)]}), broken)
    assert {f.reason for f in r.database_failures} == {"storage_error"} and r.comments_collected == []


# --- configuration -------------------------------------------------------------------------

def test_no_videos():
    with pytest.raises(ValueError, match="no videos"):
        cc.collect_comments([], client(FakeAPI({})), MemoryStore(), salt=SALT)


def test_dry_run():
    r = cc.collect_comments(refs(V1), client(FakeAPI({V1: [thread("c1", V1)]})), None, salt=SALT)
    assert r.comments_collected == ["c1"] and not r.stored and "dry run" in r.summary()


# --- with the real (throwaway) PostgreSQL ----------------------------------------------------

def test_collect_into_database_twice(db):
    repo.upsert_channels(db, [Channel(channel_id=CH, channel_name="Test", collected_at=NOW)])
    repo.upsert_videos(db, [Video(video_id=V1, channel_id=CH, title="t", published_at="2026-10-01T00:00:00Z",
                                  comment_count=3, collected_at=NOW)])
    db.commit()
    t = thread("c1", V1, author=1, replies=[comment_res("c1.r1", V1, author=2)])
    api = FakeAPI({V1: [t, thread("c2", V1, author=1)]})
    videos = cc.stored_videos(db, channel_ids=[CH])
    assert [(v.video_id, v.comment_count, v.latest_stored_comment) for v in videos] == [(V1, 3, None)]

    first = cc.collect_comments(videos, client(api), cc.supabase_store(db), salt=SALT, clock=lambda: NOW)
    second = cc.collect_comments(cc.stored_videos(db), client(api), cc.supabase_store(db), salt=SALT,
                                 clock=lambda: NOW + timedelta(hours=1))
    assert len(first.comments_inserted) == 3 and second.comments_inserted == []
    assert repo.count_rows(db, "comments") == 3
    rows = db.execute("SELECT comment_id, parent_comment_id, author_channel_id FROM research.comments "
                      "ORDER BY comment_id").fetchall()
    assert [(r[0], r[1]) for r in rows] == [("c1", None), ("c1.r1", "c1"), ("c2", None)]
    assert all(privacy.is_pseudonymized(r[2]) for r in rows)
    assert rows[0][2] == rows[2][2]  # same commenter across threads
    assert cc.stored_videos(db, new_only=True) == []  # all videos now have comments
