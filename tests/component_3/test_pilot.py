"""Tests for the STEP 26 pilot runner. Synthetic data only: no YouTube API call, no Supabase.

The pipeline part runs on the STEP 21 synthetic snapshot (channels A-F, X); collection is
replaced by a stub, and the scoped snapshot export is tested against the throwaway PostgreSQL.
"""

import json
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from research.component_3 import pilot as pl
from research.component_3.model import baselines as bl
from research.component_3.model import hgt
from research.component_3.model import metapath2vec as m2v
from shared.utils import privacy
from shared.utils import snapshots as s
from test_evaluation import CH, P, RAW, FakeEncoder, build_snapshot, ticking  # noqa: F401

SMALL = {"m2v_config": m2v.Config(walks_per_node=3, walk_length=10, dimensions=8, window=2, negative=2, epochs=2, seed=7),
         "hgt_config": hgt.HGTConfig(hidden=8, layers=1, heads=2, dropout=0.0, epochs=3, negatives_per_positive=2,
                                     validation_fraction=0.25, min_validation_edges=2, seed=3),
         "node2vec_config": bl.Node2VecConfig(dimensions=8, walk_length=10, walks_per_node=3, window=2, negative=2,
                                              epochs=2, seed=5)}
CHANNELS = {k: CH[k] for k in "ABCDEFX"}


def config(**kw):
    base = pl.PilotConfig(channel_titles=tuple(CHANNELS), n_topics=2, evaluation_sparse_fractions=(0.5,),
                          evaluation_sparse_seeds=(0,), report_path="unused.md")
    return replace(base, **kw)


@pytest.fixture
def sid(isolated_data_dir, ticking):  # noqa: F811
    return build_snapshot()


# --- configuration and quota -----------------------------------------------------------------

def test_project_pilot_config_resolves_from_channel_configuration():
    cfg = pl.load_config()
    channels = pl.resolve_channels(cfg.channel_titles)
    assert list(channels) == list(cfg.channel_titles) and len(set(channels.values())) == 3
    assert cfg.max_videos_per_channel <= 20 and cfg.stages == pl.PIPELINE_STAGES


def test_unknown_channel_title_is_refused():
    with pytest.raises(pl.PilotError, match="not a configured channel title"):
        pl.resolve_channels(("No Such Channel",))


@pytest.mark.parametrize("kw", [{"max_videos_per_channel": 0}, {"max_threads_per_video": 500},
                                {"stages": ("magic",)}, {"channel_titles": ()}, {"max_quota_units": 0}])
def test_config_validation(kw):
    with pytest.raises(pl.PilotError):
        config(**kw)


def test_quota_estimate_follows_collector_request_pattern():
    q = pl.estimate_quota(config(max_videos_per_channel=15, max_threads_per_video=50), 3)
    assert q["per_endpoint"] == {"channels.list": 2, "playlistItems.list": 3, "videos.list": 3,
                                 "commentThreads.list": 45, "comments.list": 0}
    assert q["total_upper_bound"] == 53 and q["within_cap"]
    assert pl.estimate_quota(config(fetch_all_replies=True, max_quota_units=100), 3)["within_cap"] is False


# --- preflight -------------------------------------------------------------------------------------

@contextmanager
def fake_db():
    class Conn:
        def execute(self, *_):
            class R:
                def fetchone(self):
                    return (3,)
            return R()

        def rollback(self):
            pass
    yield Conn()


def test_preflight_passes_without_printing_secrets(isolated_data_dir, monkeypatch, capsys):
    secret = "AIza" + "x" * 35
    monkeypatch.setenv("YOUTUBE_API_KEY", secret)
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://user:pw-not-real@localhost/db")
    cfg = pl.load_config()
    pre = pl.preflight(cfg, connect=fake_db)
    assert pre["ok"], pre["checks"]
    text = json.dumps(pre) + capsys.readouterr().out
    assert secret not in text and "pw-not-real" not in text and "test-salt" not in text


def test_preflight_fails_on_missing_prerequisites(isolated_data_dir, monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://user:x@localhost/db")
    pre = pl.preflight(pl.load_config(), connect=fake_db)
    status = {c["check"]: c["status"] for c in pre["checks"]}
    assert not pre["ok"] and status["environment variables"] == "fail" and status["YouTube Data API v3 client"] == "fail"


def test_failed_preflight_collects_nothing(isolated_data_dir, monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    called = []
    run = pl.run_pilot(pl.load_config(), collect_fn=lambda *a: called.append(1), write_report=False)
    assert called == [] and run["collection"] is None and run["recommendation"].startswith("remediate")


# --- pipeline on a synthetic snapshot ------------------------------------------------------------------

def test_pipeline_stages_validity_and_report(sid, tmp_path, monkeypatch):
    monkeypatch.setattr(pl, "preflight", lambda cfg, **k: {"ok": True, "checks": [], "channels": CHANNELS,
                                                            "quota": pl.estimate_quota(cfg, 7)})
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
    run = pl.run_pilot(config(report_path="docs/pilot.md"), collect_fn=lambda *a: collected, encoder=FakeEncoder(),
                       model_configs=SMALL)
    statuses = {st["stage"]: st["status"] for st in run["stages"]}
    assert set(statuses.values()) == {"completed"}, run["stages"]
    assert [v for v in run["validity"] if v["status"] != "pass"] == [], run["validity"]
    assert run["recommendation"].startswith("ready to scale")
    report = (tmp_path / "docs/pilot.md").read_text(encoding="utf-8")
    assert "| audience_bridge | completed |" in report and sid in report and "No relevance labels" in report and "## Data quality by channel" in report
    assert privacy.HASH_PREFIX not in report and not any(r in report for r in RAW.values())
    record = json.loads((pl.paths.component_dir(3) / sid / "pilot" / "pilot_run.json").read_text(encoding="utf-8"))
    assert record["snapshot_id"] == sid and not any(p in json.dumps(record) for p in P.values())


def test_failed_stage_stops_the_pipeline(sid, monkeypatch):
    from research.component_3.model import ppr_diffusion as ppr

    def boom(*a, **k):
        raise ValueError("synthetic failure for the test")
    monkeypatch.setattr(ppr, "run_diffusion", boom)
    stages, _ = pl.run_pipeline(sid, config(), encoder=FakeEncoder(), **SMALL)
    status = {st.stage: st.status for st in stages}
    assert status["hgt"] == "completed" and status["ppr_diffusion"] == "failed"
    assert {status[n] for n in ("audience_bridge", "louvain", "node2vec", "explainability", "evaluation")} == {"not_executed"}
    failed = next(st for st in stages if st.status == "failed")
    assert "synthetic failure" in failed.error and "ValueError" in failed.error


def test_disabled_stages_and_dependencies(sid):
    stages, _ = pl.run_pipeline(sid, config(stages=("research_data", "graph", "features")), encoder=FakeEncoder(), **SMALL)
    status = {st.stage: st.status for st in stages}
    assert status["graph"] == "completed" and status["topics"] == "disabled"
    assert status["audience_bridge"] == "disabled"


def test_existing_snapshots_are_not_modified(sid, monkeypatch, tmp_path):
    other = build_snapshot(interactions=[("G1", "A1"), ("G1", "B1")],
                           extracted=datetime(2026, 10, 2, tzinfo=timezone.utc))
    before = s.get_research_snapshot(other).manifest["datasets"]
    stages, _ = pl.run_pipeline(sid, config(stages=("research_data", "topics", "graph")), encoder=FakeEncoder(), **SMALL)
    assert s.get_research_snapshot(other).manifest["datasets"] == before and s.verify_research_snapshot(other).ok


# --- scoped snapshot export (throwaway PostgreSQL) ----------------------------------------------------

def test_scoped_research_snapshot_export(db, isolated_data_dir, ticking):  # noqa: F811
    from shared.database import repository as repo
    from shared.database.snapshot_export import export_research_snapshot
    from shared.schemas import Channel, Comment, Video

    at = datetime(2026, 9, 30, tzinfo=timezone.utc)
    repo.upsert_channels(db, [Channel(channel_id=CH[k], channel_name=k, collected_at=at) for k in "AB"])
    repo.upsert_videos(db, [Video(video_id=v, channel_id=CH[k], title=v, published_at=at, collected_at=at)
                            for v, k in (("A1", "A"), ("A2", "A"), ("B1", "B"))])
    repo.upsert_comments(db, [Comment(comment_id=f"c{i}", video_id=v, channel_id=CH[v[0]], author_channel_id=P["G1"],
                                      comment_text="Synthetic.", published_at=at, collected_at=at)
                              for i, v in enumerate(("A1", "A2", "B1"))])
    db.commit()
    info = export_research_snapshot(db, scope={"channels": [CH["A"]], "videos": ["A1"], "comments": ["c0"]},
                                    source="supabase_postgresql_pilot", details={"pilot": "test"})
    assert info.row_counts == {"channels": 1, "videos": 1, "comments": 1}
    assert info.source == "supabase_postgresql_pilot"
    assert info.manifest["details"]["scope"] == {"channels": 1, "videos": 1, "comments": 1}
    full = export_research_snapshot(db)
    assert full.row_counts == {"channels": 2, "videos": 3, "comments": 3}
    with pytest.raises(ValueError, match="unknown dataset"):
        export_research_snapshot(db, scope={"playlists": ["x"]})


def test_resume_requires_a_pilot_record(sid):
    with pytest.raises(pl.PilotError, match="no pilot run record"):
        pl.resume_collection(sid)


# --- full-scale experiment configuration (STEP 27) ------------------------------------------------

def test_full_experiment_config_uses_groups_and_reports_registry_gaps():
    cfg = pl.load_config(pl.paths.PROJECT_ROOT / "config/experiments/component_3_full.json")
    channels, groups, registry = pl.resolve_registry(cfg)
    assert cfg.name == "full_experiment" and cfg.snapshot_source == "supabase_postgresql_experiment"
    assert len(channels) == registry["configured_total"] and set(groups.values()) <= {"owned", "competitor"}
    assert registry["duplicate_ids"] == [] and registry["invalid_ids"] == []
    assert set(registry["gaps"]) <= {"owned", "competitor"}          # plan counts differ from the approved set
    for g, v in registry["gaps"].items():
        assert v["expected"] == dict(cfg.expected_channel_counts)[g]
    q = pl.estimate_quota(cfg, len(channels))
    videos = len(channels) * 50
    assert q["per_endpoint"]["comments.list"] == pl.math.ceil(videos * 100 * 0.0065) and q["within_cap"]


def test_reply_rate_worst_case_without_measurement():
    q = pl.estimate_quota(config(fetch_all_replies=True, max_threads_per_video=10, max_videos_per_channel=2), 1)
    assert q["per_endpoint"]["comments.list"] == 20                 # one page per thread when no rate is known


def test_channel_quality_and_distributions(sid):
    quality = pl.channel_quality(sid, CHANNELS, {i: "owned" for i in CHANNELS.values()})
    by = {q["channel"]: q for q in quality}
    assert by["A"]["videos"] == 2 and by["X"]["videos"] == 0 and by["X"]["comments"] == 0
    assert sum(q["comments"] for q in quality) == 16 and all("anon_" not in json.dumps(q) for q in quality)
    from research.component_3.model import audience_bridge as ab

    st = {"bridge": ab.run(sid, encoder=FakeEncoder(), m2v_config=SMALL["m2v_config"])}
    dist = {d["measure"]: d for d in pl.distributions(st)}
    assert 0 <= dist["audience_bridge_score"]["min"] <= dist["audience_bridge_score"]["max"] <= 1
    notes = pl.insufficient_data(st, CHANNELS)
    assert any(n.startswith("F:") and "no commenter" in n for n in notes)
    assert any(n.startswith("X:") for n in notes)


def test_resume_refuses_snapshots_from_another_run_kind(sid, monkeypatch, tmp_path):
    full = pl.load_config(pl.paths.PROJECT_ROOT / "config/experiments/component_3_full.json")
    record = pl.record_path(sid, full)
    record.parent.mkdir(parents=True)
    record.write_text(json.dumps({"snapshot_id": sid, "started_at": "x", "collection": {"snapshot_id": sid}}))
    with pytest.raises(pl.PilotError, match="was not created by a full_experiment run"):
        pl.resume_collection(sid, full)               # the synthetic snapshot's source is not an experiment
