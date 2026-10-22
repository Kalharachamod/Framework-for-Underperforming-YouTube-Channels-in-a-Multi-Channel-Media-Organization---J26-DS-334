"""Component 3 live results API (read-only view of research.c3_live_*).

TEST DATA (synthetic): two nightly runs and their scores in a throwaway local PostgreSQL (skipped without
PostgreSQL server tools). No YouTube call, no production database.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from backend.services.component_3.live_results import LiveResults

API = "/api/v1/component-3/live"
A, B = "UC" + "a" * 22, "UC" + "b" * 22


def seed(db):
    runs = [("live-20261001T183000Z", "completed", 0.4), ("live-20261002T183000Z", "completed", 0.6),
            ("live-20261003T183000Z", "failed", None)]
    for i, (rid, status, score) in enumerate(runs):
        t = datetime(2026, 10, 1 + i, 18, 30, tzinfo=timezone.utc)
        db.execute("INSERT INTO research.c3_live_runs (run_id, started_at, finished_at, status, window_start, window_end, "
                   "channels, videos, comments, error) VALUES (%s, %s, %s, %s, %s, %s, 2, 10, 50, %s)",
                   [rid, t, t, status, t, t, "network failure" if status == "failed" else None])
        if score is not None:
            for s, d, sc, shared in ((A, B, score, 3), (B, A, 0.0, 0)):
                db.execute("INSERT INTO research.c3_live_bridge_scores (run_id, source_channel_id, destination_channel_id, "
                           "source_channel_name, destination_channel_name, audience_bridge_score, confidence, "
                           "shared_commenters, rank, score_status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, 'ok')",
                           [rid, s, d, f"Channel {s[2]}", f"Channel {d[2]}", sc, 0.5 if shared else 0.0, shared])
            for c in (A, B):
                db.execute("INSERT INTO research.c3_live_channels (run_id, channel_id, channel_name, videos, comments, "
                           "unique_commenters) VALUES (%s, %s, %s, 5, 25, 20)", [rid, c, f"Channel {c[2]}"])
    db.commit()


@pytest.fixture
def client(db):
    seed(db)
    return TestClient(create_app(Settings(), live=LiveResults(connect=lambda: db)))


def test_runs_lists_newest_first_with_latest_completed(client):
    r = client.get(f"{API}/runs").json()
    assert [x["run_id"] for x in r["items"]][0] == "live-20261003T183000Z"
    assert r["latest_completed_run_id"] == "live-20261002T183000Z"
    assert r["items"][0]["status"] == "failed" and r["items"][0]["error"] == "network failure"


def test_bridges_of_latest_completed_run(client):
    r = client.get(f"{API}/bridges").json()
    assert r["run"]["run_id"] == "live-20261002T183000Z"
    assert r["items"][0]["source_channel_id"] == A and r["items"][0]["audience_bridge_score"] == 0.6
    assert r["pairs"] == 2 and r["pairs_with_evidence"] == 1 and len(r["channels"]) == 2
    older = client.get(f"{API}/bridges", params={"run_id": "live-20261001T183000Z", "source": A}).json()
    assert older["items"][0]["audience_bridge_score"] == 0.4 and len(older["items"]) == 1


def test_history_returns_the_pair_trend_oldest_first(client):
    r = client.get(f"{API}/history", params={"source": A, "destination": B}).json()
    assert [x["audience_bridge_score"] for x in r["items"]] == [0.4, 0.6]


def test_invalid_and_missing(client):
    assert client.get(f"{API}/bridges", params={"run_id": "bad"}).status_code == 422
    assert client.get(f"{API}/bridges", params={"run_id": "live-20261003T183000Z"}).status_code == 404   # failed run
    assert client.get(f"{API}/history", params={"source": A, "destination": A}).status_code == 422
    assert client.get(f"{API}/bridges", params={"source": "not a channel"}).status_code == 422


def test_unconfigured_database_is_a_clear_503():
    def broken():
        raise RuntimeError("no SUPABASE_DB_URL")
    c = TestClient(create_app(Settings(), live=LiveResults(connect=broken)))
    r = c.get(f"{API}/bridges")
    assert r.status_code == 503 and r.json()["error"]["code"] == "storage_unavailable"
    assert "postgresql://" not in r.text


def test_offline_copy_is_served_when_the_database_is_unreachable(db, tmp_path):
    seed(db)
    state = {"up": True}

    def connect():
        if not state["up"]:
            raise RuntimeError("network blocks PostgreSQL")
        return db

    c = TestClient(create_app(Settings(), live=LiveResults(connect=connect, cache_dir=tmp_path)))
    first = c.get(f"{API}/bridges").json()
    assert "offline" not in first
    state["up"] = False
    r = c.get(f"{API}/bridges")
    assert r.status_code == 200 and r.json()["offline"]["saved_at"]
    assert r.json()["items"] == first["items"]
    never_saved = c.get(f"{API}/history", params={"source": A, "destination": B})
    assert never_saved.status_code == 503 and "not reachable" in never_saved.json()["error"]["message"]
    assert not any("anon_" in p.read_text() for p in tmp_path.iterdir())   # aggregates only
