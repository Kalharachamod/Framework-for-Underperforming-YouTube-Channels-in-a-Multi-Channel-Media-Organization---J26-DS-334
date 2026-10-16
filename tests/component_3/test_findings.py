"""Tests for the STEP 28 findings report. Synthetic data only (the STEP 21 fixture snapshot run
through the STEP 26/27 runner with a stubbed collection); these are not research findings."""

import json

import pytest

from research.component_3 import findings as fd
from research.component_3 import pilot as pl
from shared.utils import privacy
from shared.utils import snapshots as s
from test_evaluation import P, RAW, FakeEncoder, build_snapshot, ticking  # noqa: F401
from test_pilot import CHANNELS, SMALL


def experiment_config(tmp_path):
    cfg = {"name": "full_experiment", "title": "Synthetic full experiment", "channel_groups": ["owned"],
           "snapshot_source": "synthetic_test", "expected_channel_counts": {},
           "collection": {"max_videos_per_channel": 50, "max_threads_per_video": 100},
           "pipeline": {"n_topics": 2, "evaluation_sparse_fractions": [0.5], "evaluation_sparse_seeds": [0]},
           "report_path": "docs/experiment.md"}
    path = tmp_path / "experiment.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return path


@pytest.fixture
def completed(isolated_data_dir, ticking, tmp_path, monkeypatch):  # noqa: F811
    sid = build_snapshot()
    cfg_path = experiment_config(tmp_path)
    cfg = pl.load_config(cfg_path)
    monkeypatch.setattr(pl, "preflight", lambda c, **k: {
        "ok": True, "checks": [], "channels": CHANNELS, "groups": {i: "owned" for i in CHANNELS.values()},
        "registry": {"configured_by_group": {"owned": 7}, "gaps": {}}, "quota": pl.estimate_quota(c, 7)})
    collected = {"snapshot_id": sid, "snapshot_rows": s.get_research_snapshot(sid).row_counts, "seconds": 0.1,
                 "channels": {"requested": 7, "collected": 7, "failed": []},
                 "videos": {"collected": 7, "inserted": 7, "updated": 0, "unchanged": 0, "channel_failures": [],
                            "video_failures": []},
                 "comments": {"collected": 16, "top_level": 16, "replies": 0, "inserted": 16, "updated": 0,
                              "skipped_entries": 0, "videos_processed": 7, "videos_with_zero_public_comments": 0,
                              "videos_with_comments_disabled": 0, "videos_with_unknown_public_count": 7,
                              "video_failures": [], "comment_failures": []},
                 "requests": {"total": 0, "succeeded": 0, "failed": 0, "retries": 0, "quota_units": 0, "by_endpoint": {}}}
    monkeypatch.setattr(pl.paths, "PROJECT_ROOT", tmp_path)
    run = pl.run_pilot(cfg, collect_fn=lambda *a: collected, encoder=FakeEncoder(), model_configs=SMALL)
    assert all(st["status"] == "completed" for st in run["stages"]), run["stages"]
    return sid, cfg_path, tmp_path


def test_findings_report_from_stored_artifacts(completed):
    sid, cfg_path, root = completed
    out = fd.generate(sid, config_path=cfg_path)
    report = (root / fd.REPORT_PATH).read_text(encoding="utf-8")
    for section in ("## 1. Executive summary", "## 2. Experiment configuration and provenance", "## 7. Baseline comparison",
                    "## 9. Robustness and temporal analysis", "## 11. Limitations and validity threats",
                    "**Finding 4 — Baseline comparison.**"):
        assert section in report
    assert sid in report and "not computed (no labels)" in report
    assert len(out["figures"]) >= 5 and all((root / fd.FIGURES_DIR / sid / p.split("\\")[-1].split("/")[-1]).is_file()
                                            for p in out["figures"])
    assert f"](figures/component_3/{sid}/abs_distribution.png)" in report      # relative to docs/
    stats = json.loads(open(out["stats"], encoding="utf-8").read())
    assert stats["snapshot_id"] == sid and stats["pairs"]["scored"] > 0


def test_report_numbers_match_stored_artifacts(completed):
    from research.component_3.model import audience_bridge as ab

    sid, cfg_path, _ = completed
    res = fd.generate(sid, config_path=cfg_path)["results"]
    bridge = ab.load(ab.bridge_dir(sid, res["ids"]["audience_bridge"]))
    ok = bridge.scores[bridge.scores.score_status == "ok"]
    assert res["pairs"]["scored"] == len(ok)
    assert res["distributions"]["audience_bridge_score"]["median"] == pytest.approx(float(ok.audience_bridge_score.median()))
    top = {t["source"]: t["destination"] for t in res["top_destinations"]}
    assert top["A"] in ("B", "C") and "F" in res["structural"]["disconnected"]
    assert res["relevance"]["computed"] is False


def test_no_identifiers_in_report_or_stats(completed):
    sid, cfg_path, root = completed
    out = fd.generate(sid, config_path=cfg_path)
    text = (root / fd.REPORT_PATH).read_text(encoding="utf-8") + open(out["stats"], encoding="utf-8").read()
    assert privacy.HASH_PREFIX not in text and "commenter:" not in text
    assert not any(v in text for v in list(RAW.values()) + list(P.values()))


def test_incomplete_or_missing_experiment_is_refused(completed, monkeypatch):
    sid, cfg_path, _ = completed
    with pytest.raises(fd.FindingsError, match="no full_experiment run record"):
        fd.generate("rs-20990101T000000Z", config_path=cfg_path)
    cfg = pl.load_config(cfg_path)
    rec = pl.record_path(sid, cfg)
    run = json.loads(rec.read_text(encoding="utf-8"))
    run["stages"][-1]["status"] = "failed"
    rec.write_text(json.dumps(run), encoding="utf-8")
    with pytest.raises(fd.FindingsError, match="incomplete"):
        fd.generate(sid, config_path=cfg_path)
