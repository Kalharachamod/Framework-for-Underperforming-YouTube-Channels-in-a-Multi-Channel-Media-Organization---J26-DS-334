"""Tests for the collection pipeline runner (stand-in stages; no API, no database)."""

import json

from shared.data_collection import channel_collector, comment_collector, run_collection, video_collector
from research.component_3.preprocessing import research_dataset


def stub(monkeypatch, codes):
    calls = []

    def make(name):
        def fake(argv):
            calls.append((name, list(argv)))
            return codes.get(name, 0)
        return fake

    monkeypatch.setattr(channel_collector, "main", make("channels"))
    monkeypatch.setattr(video_collector, "main", make("videos"))
    monkeypatch.setattr(comment_collector, "main", make("comments"))
    monkeypatch.setattr(research_dataset, "main", make("research_snapshot"))
    return calls


def test_runs_all_stages_in_order_and_logs(monkeypatch, isolated_data_dir):
    calls = stub(monkeypatch, {})
    assert run_collection.main(["--group", "owned", "--max-videos", "20", "--snapshot"]) == 0
    assert [c[0] for c in calls] == ["channels", "videos", "comments", "research_snapshot"]
    assert calls[1][1] == ["--group", "owned", "--max-videos", "20"]
    assert "--incremental" in calls[2][1]
    log = json.loads(next((isolated_data_dir / "raw" / "collection_runs").iterdir()).read_text())
    assert [s["stage"] for s in log["stages"]] == ["channels", "videos", "comments", "research_snapshot"]


def test_partial_failure_continues_but_reports(monkeypatch, isolated_data_dir):
    calls = stub(monkeypatch, {"videos": 1})
    assert run_collection.main([]) == 1
    assert [c[0] for c in calls] == ["channels", "videos", "comments"]


def test_stage_that_cannot_run_stops_pipeline(monkeypatch, isolated_data_dir):
    calls = stub(monkeypatch, {"channels": 2})
    assert run_collection.main(["--snapshot"]) == 1
    assert [c[0] for c in calls] == ["channels"]
