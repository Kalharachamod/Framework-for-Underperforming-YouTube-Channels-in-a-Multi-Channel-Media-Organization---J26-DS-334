"""Tests for the channel collector and channel configuration.

No real YouTube API calls (mocked HTTP transport) and no real Supabase
(a mocked store, or the throwaway local PostgreSQL from conftest).
All channels are TEST DATA with synthetic ids.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from shared.data_collection import channel_collector as cc
from shared.data_collection import channel_config as cfg
from shared.data_collection import youtube_client as yc
from shared.data_collection.youtube_client import HttpResult, RetryPolicy, YouTubeClient
from shared.database import repository as repo

NOW = datetime(2026, 10, 8, 6, 0, tzinfo=timezone.utc)


def item(cid, title=None, subs="1000", hidden=False, **stats):
    return {
        "kind": "youtube#channel", "id": cid,
        "snippet": {"title": f"Test {cid}" if title is None else title, "description": "Synthetic channel.",
                    "publishedAt": "2015-03-01T10:00:00Z", "customUrl": "@x"},
        "statistics": {"viewCount": stats.get("views", "50000"), "videoCount": stats.get("videos", "120"),
                       "hiddenSubscriberCount": hidden, **({} if hidden else {"subscriberCount": subs})},
    }


class FakeAPI:
    """Mocked YouTube HTTP transport: serves known channels; can be told to fail."""

    def __init__(self, channels=None, fail=None):
        self.channels = {c["id"]: c for c in (channels or [])}
        self.fail = list(fail or [])  # queue of HttpResult / exceptions returned before normal answers
        self.calls = []

    def __call__(self, url, params, timeout):
        self.calls.append(dict(params))
        if self.fail:
            f = self.fail.pop(0)
            if isinstance(f, BaseException):
                raise f
            return f
        ids = params["id"].split(",")
        body = {"kind": "youtube#channelListResponse",
                "items": [self.channels[i] for i in ids if i in self.channels]}
        return HttpResult(200, {}, json.dumps(body).encode())


def error(status, reason=None):
    body = {"error": {"code": status, "message": "x", "errors": [{"reason": reason}] if reason else []}}
    return HttpResult(status, {}, json.dumps(body).encode())


def client(api, retries=0):
    return YouTubeClient(api_key="TEST_KEY_not_real", transport=api, sleep=lambda s: None,
                         retry=RetryPolicy(max_retries=retries))


class MemoryStore:
    """Mocked persistence: records what would be written, with upsert semantics."""

    def __init__(self):
        self.rows, self.calls = {}, 0

    def __call__(self, channels):
        self.calls += 1
        ins, upd, chg = [], [], []
        for c in channels:
            old = self.rows.get(c.channel_id)
            (upd if old else ins).append(c.channel_id)
            if old and old.model_dump(exclude={"collected_at"}) != c.model_dump(exclude={"collected_at"}):
                chg.append(c.channel_id)
            self.rows[c.channel_id] = c
        ref = [i for i in upd if i not in chg]
        return repo.WriteSummary("channels", len(channels), len(ins), len(upd), 0,
                                 tuple(ins), tuple(upd), tuple(chg), tuple(ref))


def clock_at(t=NOW):
    return lambda: t


# --- successful collection ------------------------------------------------------------

def test_successful_collection():
    api, store = FakeAPI([item("UC_test_a")]), MemoryStore()
    r = cc.collect_channels(["UC_test_a"], client(api), store, clock=clock_at())
    assert r.ok and r.collected == ["UC_test_a"] and r.inserted == ["UC_test_a"]
    ch = store.rows["UC_test_a"]
    assert ch.channel_name == "Test UC_test_a" and ch.subscriber_count == 1000
    assert ch.view_count == 50000 and ch.video_count == 120
    assert ch.description == "Synthetic channel."
    assert ch.published_at == datetime(2015, 3, 1, 10, tzinfo=timezone.utc)


def test_requests_only_needed_parts_and_never_search():
    api = FakeAPI([item("UC_test_a")])
    c = client(api)
    cc.collect_channels(["UC_test_a"], c, MemoryStore())
    assert api.calls[0]["part"] == "snippet,statistics"
    assert all(r.resource == "channels" for r in c.request_log)


def test_collected_at_is_set_and_separate_from_published_at():
    api, store = FakeAPI([item("UC_test_a")]), MemoryStore()
    r = cc.collect_channels(["UC_test_a"], client(api), store, clock=clock_at())
    ch = store.rows["UC_test_a"]
    assert ch.collected_at == NOW and ch.collected_at.utcoffset() == timedelta(0)
    assert ch.published_at != ch.collected_at
    assert r.started_at == "2026-10-08T06:00:00Z"


def test_hidden_subscriber_count_is_none_not_zero():
    api, store = FakeAPI([item("UC_test_a", hidden=True)]), MemoryStore()
    cc.collect_channels(["UC_test_a"], client(api), store)
    assert store.rows["UC_test_a"].subscriber_count is None


def test_multiple_channels_batched_50_per_request():
    ids = [f"UC_test_{i:03d}" for i in range(120)]
    api, store = FakeAPI([item(i) for i in ids]), MemoryStore()
    c = client(api)
    r = cc.collect_channels(ids, c, store)
    assert len(api.calls) == 3  # 50 + 50 + 20
    assert r.quota_used == 3
    assert sorted(r.collected) == sorted(ids) and len(store.rows) == 120


def test_duplicate_ids_in_config_requested_once():
    api = FakeAPI([item("UC_test_a")])
    r = cc.collect_channels(["UC_test_a", "UC_test_a", " UC_test_a "], client(api), MemoryStore())
    assert r.requested == ["UC_test_a"] and api.calls[0]["id"] == "UC_test_a"


# --- repeat execution ---------------------------------------------------------------

def test_second_run_updates_not_duplicates():
    store = MemoryStore()
    cc.collect_channels(["UC_test_a"], client(FakeAPI([item("UC_test_a", subs="1000")])), store)
    r = cc.collect_channels(["UC_test_a"], client(FakeAPI([item("UC_test_a", subs="1500")])), store,
                            clock=clock_at(NOW + timedelta(days=1)))
    assert r.updated == ["UC_test_a"] and r.inserted == []
    assert r.changed == ["UC_test_a"] and r.refreshed == []
    assert len(store.rows) == 1 and store.rows["UC_test_a"].subscriber_count == 1500


# --- failures ---------------------------------------------------------------------

def test_invalid_and_unknown_channels():
    api, store = FakeAPI([item("UC_test_a")]), MemoryStore()
    r = cc.collect_channels(["UC_test_a", "bad id!", "UC_test_missing"], client(api), store)
    reasons = {f.channel_id: f.reason for f in r.failed}
    assert reasons == {"bad id!": "invalid_id", "UC_test_missing": "not_found"}
    assert r.collected == ["UC_test_a"]  # the valid channel was still collected
    assert "bad id!" not in api.calls[0]["id"]  # invalid id never sent to the API


def test_validation_failure_not_persisted():
    bad = item("UC_test_bad", views="-5")
    blank = item("UC_test_blank", title="")
    api, store = FakeAPI([item("UC_test_a"), bad, blank]), MemoryStore()
    r = cc.collect_channels(["UC_test_a", "UC_test_bad", "UC_test_blank"], client(api), store)
    reasons = {f.channel_id: (f.reason, f.message) for f in r.failed}
    assert reasons["UC_test_bad"][0] == "validation_error" and "view_count" in reasons["UC_test_bad"][1]
    assert reasons["UC_test_blank"][0] == "validation_error" and "channel_name" in reasons["UC_test_blank"][1]
    assert set(store.rows) == {"UC_test_a"}


def test_malformed_api_response():
    api = FakeAPI(fail=[HttpResult(200, {}, b"<html>oops</html>")])
    r = cc.collect_channels(["UC_test_a"], client(api), MemoryStore())
    assert r.failed[0].reason == "api_error" and "not a JSON" in r.failed[0].message


@pytest.mark.parametrize("response, reason, stops_run", [
    (error(403, "quotaExceeded"), "quota_exceeded", True),
    (error(400, "keyInvalid"), "auth_error", True),
    (error(401), "auth_error", True),
    (error(403, "forbidden"), "api_error", False),
    (error(404, "channelNotFound"), "api_error", False),
    (error(429), "api_error", False),
    (error(500), "api_error", False),
    (error(503), "api_error", False),
    (TimeoutError(), "api_error", False),
    (ConnectionResetError("reset"), "api_error", False),
])
def test_api_failures(response, reason, stops_run):
    batch1 = [f"UC_test_{i:03d}" for i in range(50)]
    batch2 = ["UC_test_next"]
    api = FakeAPI([item(i) for i in batch1 + batch2], fail=[response])
    store = MemoryStore()
    r = cc.collect_channels(batch1 + batch2, client(api), store)
    assert {f.reason for f in r.failed} == {reason}
    assert len(r.failed) == 50  # the whole failed batch is reported per channel
    if stops_run:
        assert r.skipped == batch2 and store.calls == 0  # no point calling the API again
    else:
        assert r.collected == batch2 and set(store.rows) == {"UC_test_next"}  # next batch still processed
    assert not r.ok


def test_transient_failure_recovered_by_client_retry():
    api = FakeAPI([item("UC_test_a")], fail=[error(503)])
    r = cc.collect_channels(["UC_test_a"], client(api, retries=2), MemoryStore())
    assert r.ok and r.collected == ["UC_test_a"] and len(api.calls) == 2


def test_storage_failure_reported():
    def broken_store(channels):
        raise repo.ReferentialIntegrityError("db down (test)")
    r = cc.collect_channels(["UC_test_a"], client(FakeAPI([item("UC_test_a")])), broken_store)
    assert r.failed[0].reason == "storage_error" and r.collected == []


def test_api_key_not_in_results():
    api = FakeAPI(fail=[HttpResult(400, {}, json.dumps({"error": {"code": 400, "message":
        "bad key=TEST_KEY_not_real", "errors": [{"reason": "badRequest"}]}}).encode())])
    r = cc.collect_channels(["UC_test_a"], client(api), MemoryStore())
    assert "TEST_KEY_not_real" not in r.summary() + repr(r)


def test_empty_channel_list():
    with pytest.raises(ValueError, match="no channel ids"):
        cc.collect_channels([], client(FakeAPI()), MemoryStore())


def test_dry_run_stores_nothing():
    r = cc.collect_channels(["UC_test_a"], client(FakeAPI([item("UC_test_a")])), None)
    assert r.collected == ["UC_test_a"] and not r.stored and r.inserted == []
    assert "dry run" in r.summary()


# --- with the real (throwaway) PostgreSQL ------------------------------------------------

def test_collect_into_database_twice_no_duplicates(db):
    api = FakeAPI([item("UC_test_a", subs="1000"), item("UC_test_b")])
    first = cc.collect_channels(["UC_test_a", "UC_test_b"], client(api), cc.supabase_store(db), clock=clock_at())
    api.channels["UC_test_a"] = item("UC_test_a", subs="1300")
    second = cc.collect_channels(["UC_test_a", "UC_test_b"], client(api), cc.supabase_store(db),
                                 clock=clock_at(NOW + timedelta(days=1)))
    assert sorted(first.inserted) == ["UC_test_a", "UC_test_b"]
    # A new collection refreshes collected_at, so both current rows are updated (no new rows) ...
    assert sorted(second.updated) == ["UC_test_a", "UC_test_b"] and second.inserted == []
    # ... but only a's values changed; b was re-observed with identical values.
    assert second.changed == ["UC_test_a"] and second.refreshed == ["UC_test_b"]
    assert "values changed 1, refreshed only 1" in second.summary()
    assert repo.count_rows(db, "channels") == 2
    a = repo.get_channel(db, "UC_test_a")
    assert a.subscriber_count == 1300 and a.description == "Synthetic channel."
    assert a.published_at == datetime(2015, 3, 1, 10, tzinfo=timezone.utc)
    assert [h["subscriber_count"] for h in repo.stats_history(db, "channels", "UC_test_a")] == [1000, 1300]


# --- configuration -----------------------------------------------------------------------

@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg.paths, "PROJECT_ROOT", tmp_path)
    (tmp_path / "config" / "organizations").mkdir(parents=True)
    (tmp_path / "config" / "organizations" / "testorg.json").write_text(json.dumps(
        {"organization": "Testorg", "channels": [{"channel_id": "UC_test_a"}, {"channel_id": "UC_test_b"}]}))
    return tmp_path


def write_config(root, groups):
    (root / "config" / "research_channels.json").write_text(json.dumps({"groups": groups}))


def test_config_groups(project):
    write_config(project, {"owned": {"organizations": ["testorg"], "channel_ids": ["UC_test_extra"]},
                           "competitor": {"organizations": [], "channel_ids": ["UC_test_comp"]}})
    chans = cfg.load_channels()
    assert [(c.channel_id, c.group) for c in chans] == [
        ("UC_test_a", "owned"), ("UC_test_b", "owned"), ("UC_test_extra", "owned"), ("UC_test_comp", "competitor")]
    assert chans[0].source == "organization:testorg"
    assert [c.channel_id for c in cfg.load_channels(["competitor"])] == ["UC_test_comp"]


def test_config_errors(project):
    with pytest.raises(cfg.ChannelConfigError, match="not found"):
        cfg.load_channels()
    write_config(project, {"owned": {"organizations": [], "channel_ids": []}})
    with pytest.raises(cfg.ChannelConfigError, match="no channels configured"):
        cfg.load_channels()
    write_config(project, {"owned": {"channel_ids": ["UC_test_a"]}, "competitor": {"channel_ids": ["UC_test_a"]}})
    with pytest.raises(cfg.ChannelConfigError, match="both"):
        cfg.load_channels()
    write_config(project, {"owned": {"channel_ids": ["bad id"]}})
    with pytest.raises(cfg.ChannelConfigError, match="invalid channel id"):
        cfg.load_channels()
    write_config(project, {"owned": {"organizations": ["nothere"]}})
    with pytest.raises(cfg.ChannelConfigError, match="no confirmed list"):
        cfg.load_channels()
    with pytest.raises(cfg.ChannelConfigError, match="unknown group"):
        write_config(project, {"owned": {"channel_ids": ["UC_test_a"]}})
        cfg.load_channels(["partners"])


def test_repository_config_is_valid():
    """The committed config resolves (18 confirmed Derana channels as 'owned')."""
    chans = cfg.load_channels()
    assert {c.group for c in chans} == {"owned"} and len(chans) >= 1
    assert all(yc.is_valid_id(c.channel_id) for c in chans)


# --- command line ----------------------------------------------------------------------------

def test_cli_empty_config_is_clear_error(project, capsys):
    write_config(project, {"owned": {"channel_ids": []}})
    assert cc.main(["--dry-run"]) == 2
    assert "no channels configured" in capsys.readouterr().err


def test_cli_dry_run(project, monkeypatch, capsys):
    write_config(project, {"owned": {"organizations": ["testorg"]}})
    monkeypatch.setattr(cc.yc, "YouTubeClient", lambda: client(FakeAPI([item("UC_test_a"), item("UC_test_b")])))
    assert cc.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Collecting 2 channel(s)" in out and "dry run" in out and "collected 2" in out
