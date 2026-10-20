"""Component 3 live results (nightly job): rolling-window snapshot, publishing and run records.

TEST DATA (synthetic): the research-dataset fixture channels A, B, C in a throwaway local PostgreSQL
(skipped without PostgreSQL server tools). No YouTube call (collection off) and no pipeline run: the
scoring step is replaced by a known score table, so only the live job's own logic is tested.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from research.component_3 import live
from shared.database import repository as repo
from test_research_dataset import channels, comments, ticking, videos  # noqa: F401  (shared synthetic fixture)

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
IDS = ["UC_test_A", "UC_test_B", "UC_test_C"]


def fake_bridge(snapshot_id, **kw):
    rows = []
    for s in IDS:
        for d in IDS:
            if s != d:
                shared = 2 if {s, d} == {"UC_test_A", "UC_test_B"} else 1
                rows.append({"source_channel_id": f"channel:{s}", "destination_channel_id": f"channel:{d}",
                             "audience_bridge_score": 0.5 * shared / 2, "base_score": 0.6, "diffusion_contribution": 0.2,
                             "embedding_contribution": 0.2, "topic_contribution": 0.2, "confidence": shared / (shared + 3),
                             "shared_commenters": shared, "rank": 1 if shared == 2 else 2, "score_status": "ok"})
    return SimpleNamespace(scores=pd.DataFrame(rows), experiment_id="abs-000000000000")


@pytest.fixture
def seeded(db, isolated_data_dir, ticking, monkeypatch):  # noqa: F811
    repo.upsert_channels(db, channels())
    repo.upsert_videos(db, videos())
    repo.upsert_comments(db, comments())
    db.commit()
    monkeypatch.setattr(live, "research_channel_ids", lambda: list(IDS))
    monkeypatch.setattr(live, "score", fake_bridge)

    @contextmanager
    def database():
        yield db

    return db, database


def test_run_id_and_validation():
    assert live.run_id_for(NOW) == "live-20260930T120000Z"
    with pytest.raises(live.LiveError):
        live.run_nightly(window_days=0, collect_data=False)


def test_nightly_publishes_scores_channels_and_run_record(seeded):
    db, database = seeded
    out = live.run_nightly(collect_data=False, window_days=60, database=database, now=NOW, log=lambda m: None)
    assert out["status"] == "completed" and out["pairs"] == 6
    run = db.execute("SELECT status, snapshot_id, channels, videos, experiment_id, error FROM research.c3_live_runs "
                     "WHERE run_id = %s", [out["run_id"]]).fetchone()
    assert run[0] == "completed" and run[1] == out["snapshot_id"] and run[2] == 3 and run[3] == 4
    assert run[4] == "abs-000000000000" and run[5] is None
    top = db.execute("SELECT source_channel_id, destination_channel_id, source_channel_name, shared_commenters "
                     "FROM research.c3_live_bridge_scores WHERE run_id = %s ORDER BY audience_bridge_score DESC, "
                     "source_channel_id LIMIT 1", [out["run_id"]]).fetchone()
    assert top[0] == "UC_test_A" and top[1] == "UC_test_B" and top[2] == "Test UC_test_A" and top[3] == 2
    chans = dict(db.execute("SELECT channel_id, comments FROM research.c3_live_channels WHERE run_id = %s",
                            [out["run_id"]]).fetchall())
    assert set(chans) == set(IDS) and sum(chans.values()) > 0
    text = " ".join(str(r) for r in db.execute("SELECT * FROM research.c3_live_bridge_scores").fetchall())
    assert "anon_" not in text                                     # aggregates only, never commenter ids


def test_window_without_videos_records_a_failed_run(seeded):
    db, database = seeded
    with pytest.raises(live.LiveError, match="no videos published"):
        live.run_nightly(collect_data=False, window_days=5, database=database, now=NOW, log=lambda m: None)
    status, error = db.execute("SELECT status, error FROM research.c3_live_runs ORDER BY started_at DESC LIMIT 1").fetchone()
    assert status == "failed" and "no videos published" in error
    assert db.execute("SELECT count(*) FROM research.c3_live_bridge_scores").fetchone()[0] == 0   # no partial results


def test_collection_failing_for_every_channel_fails_the_run(seeded, monkeypatch):
    from shared.data_collection import channel_collector as chc

    db, database = seeded
    def rejected(ids, client, store):
        return chc.ChannelCollectionResult(requested=list(ids), failed=[
            chc.ChannelFailure(cid, "auth_error", "API key not valid") for cid in ids])
    monkeypatch.setattr(chc, "collect_channels", rejected)
    with pytest.raises(live.LiveError, match="collection failed for all 3 channels"):
        live.run_nightly(client=SimpleNamespace(quota_used=1), database=database, now=NOW, log=lambda m: None)
    status, error = db.execute("SELECT status, error FROM research.c3_live_runs ORDER BY started_at DESC LIMIT 1").fetchone()
    assert status == "failed" and "auth_error: API key not valid" in error
    assert db.execute("SELECT count(*) FROM research.c3_live_bridge_scores").fetchone()[0] == 0
