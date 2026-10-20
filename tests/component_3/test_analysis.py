"""Quick organization analysis (research.component_3.analysis) without network or database.

TEST DATA: none (configuration and validation only); the pipeline progress hook is exercised on a
snapshot id that does not exist, so the stage fails and is reported, never silently skipped.
"""

import pytest

from research.component_3 import analysis as an
from research.component_3 import pilot as pl

CH1, CH2 = "UC" + "a" * 22, "UC" + "b" * 22


def test_quick_config_is_fast_and_scoped():
    cfg = an.quick_config("Sirasa", ["Sirasa TV", "Shakthi TV"])
    assert cfg.max_videos_per_channel == 15 and cfg.max_threads_per_video == 50 and not cfg.fetch_all_replies
    assert cfg.snapshot_source == an.SNAPSHOT_SOURCE
    assert not {"hgt", "node2vec", "evaluation"} & set(cfg.stages)
    assert {"topics", "metapath2vec", "ppr_diffusion", "audience_bridge", "explainability"} <= set(cfg.stages)
    assert pl.estimate_quota(cfg, an.MAX_CHANNELS)["within_cap"]   # the largest allowed job fits the cap


@pytest.mark.parametrize("channels, message", [
    ({CH1: "A"}, "between 2 and"),
    ({f"UC{i:022d}": str(i) for i in range(an.MAX_CHANNELS + 1)}, "between 2 and"),
    ({CH1: "A", "bad id!": "B"}, "not valid"),
])
def test_validate_channels(channels, message):
    with pytest.raises(an.AnalysisError, match=message):
        an.validate_channels(channels)


def test_validate_channels_accepts_two():
    an.validate_channels({CH1: "A", CH2: "B"})


def test_every_step_has_a_label():
    assert set(an.STEPS) | set(an.COMPLETE_STEPS) == set(an.STEP_LABELS)
    assert not set(an.STEPS) & set(an.COMPLETE_STEPS)        # completion adds exactly what quick skips


def test_complete_refuses_research_snapshots(isolated_data_dir):
    with pytest.raises(Exception):
        an.complete_analysis("rs-20990101T000000Z")


def test_run_pipeline_reports_progress(isolated_data_dir):
    seen = []
    cfg = an.quick_config("Sirasa", ["A", "B"])
    results, _ = pl.run_pipeline("rs-20990101T000000Z", cfg, on_stage=lambda r: seen.append((r.stage, r.status)))
    assert seen[:2] == [("research_data", "running"), ("research_data", "failed")]
    assert results[0].status == "failed" and all(r.status == "not_executed" for r in results[1:]
                                                 if r.stage in cfg.stages)


# --- completing a quick analysis: the proposed method must be evaluated -----------------------------

def _stub_completion(monkeypatch, tmp_path, methods):
    """Replace the heavy stages with stubs; only the decision logic of complete_analysis runs."""
    from types import SimpleNamespace

    from research.component_3.evaluation import evaluate as ev
    from research.component_3.model import baselines as bl
    from research.component_3.model import hgt
    from research.component_3.model import metapath2vec as m2v
    from research.component_3.preprocessing import hetero_graph as hg
    from shared.utils import snapshots

    done = tmp_path / "done"
    done.mkdir()
    for f in ("experiment.json", "model.pt"):
        (done / f).write_text("{}", encoding="utf-8")
    monkeypatch.setattr(snapshots, "get_research_snapshot", lambda sid: SimpleNamespace(
        source=an.SNAPSHOT_SOURCE, manifest={"details": {"organization": "Testorg"}}))
    monkeypatch.setattr(hg, "load_graph", lambda d: object())
    monkeypatch.setattr(an, "_load_encoder", lambda: None)
    monkeypatch.setattr(hgt, "make_experiment_id", lambda g, c: "hgt-000000000000")
    monkeypatch.setattr(m2v, "embeddings_dir", lambda s, e: done)                 # HGT already saved: reused
    monkeypatch.setattr(bl, "load_input", lambda s: None)
    monkeypatch.setattr(bl, "run_node2vec", lambda i, c: SimpleNamespace(experiment_id="node2vec-000000000000"))
    monkeypatch.setattr(bl, "baseline_dir", lambda s, e: done)                    # node2vec already saved
    monkeypatch.setattr(an, "organization_snapshots", lambda org: [])
    monkeypatch.setattr(ev, "evaluate", lambda *a, **k: SimpleNamespace(
        evaluation_id="eval-000000000000", metadata={"methods": methods, "temporal": {"status": "skipped"}}))
    monkeypatch.setattr(ev, "save", lambda r: None)


def test_complete_fails_when_the_score_cannot_be_evaluated(monkeypatch, tmp_path):
    _stub_completion(monkeypatch, tmp_path, {
        "audience_bridge_score": {"status": "failed", "reason": "ValueError: model files could not be loaded"},
        "louvain": {"status": "ok"}})
    seen = []
    with pytest.raises(an.AnalysisError, match="could not score the Audience Bridge Score"):
        an.complete_analysis("rs-20261016T095457Z", lambda step, status, d: seen.append((step, status)))
    assert ("evaluation", "failed") in seen and ("evaluation", "completed") not in seen


def test_complete_reports_other_failed_methods_as_warnings(monkeypatch, tmp_path):
    _stub_completion(monkeypatch, tmp_path, {"audience_bridge_score": {"status": "ok"},
                                             "node2vec": {"status": "failed", "reason": "MemoryError"}})
    details = {}
    out = an.complete_analysis("rs-20261016T095457Z", lambda step, status, d: details.update({(step, status): d}))
    assert out["evaluation"] == "eval-000000000000"
    assert details[("evaluation", "completed")]["failed_methods"] == ["node2vec"]


def test_comment_collection_reports_progress_per_channel(monkeypatch):
    """Channels finish one after another; a channel without videos counts as done (stubs, no network)."""
    from contextlib import contextmanager
    from types import SimpleNamespace

    from shared.data_collection import channel_collector as chc
    from shared.data_collection import video_collector as vc
    from shared.data_collection import youtube_comment_collector as cmc
    from shared.database import snapshot_export

    ch3 = "UC" + "c" * 22
    channels = {CH1: "A", CH2: "B", ch3: "C (no videos)"}
    refs = [SimpleNamespace(video_id=f"v{i}", channel_id=CH1 if i < 3 else CH2) for i in range(5)]
    monkeypatch.setattr(chc, "collect_channels", lambda ids, client, store: SimpleNamespace(collected=list(ids), failed=[]))
    monkeypatch.setattr(chc, "supabase_store", lambda conn: None)
    monkeypatch.setattr(vc, "supabase_store", lambda conn: None)
    monkeypatch.setattr(vc, "supabase_known_channels", lambda conn: None)
    monkeypatch.setattr(vc, "collect_videos", lambda *a, **k: SimpleNamespace(
        videos_collected=[r.video_id for r in refs], video_failures=[], channel_failures=[]))
    monkeypatch.setattr(cmc, "stored_videos", lambda conn, video_ids: refs)
    monkeypatch.setattr(cmc, "supabase_store", lambda conn: None)
    monkeypatch.setattr(cmc, "collect_comments", lambda batch, *a, **k: SimpleNamespace(
        comments_collected=[f"c-{r.video_id}" for r in batch], videos_with_comments_disabled=[], video_failures=[],
        comment_failures=[]))
    monkeypatch.setattr(snapshot_export, "export_research_snapshot", lambda conn, **k: SimpleNamespace(
        snapshot_id="rs-20990101T000000Z", row_counts={"channels": 3, "videos": 5, "comments": 5}))

    @contextmanager
    def fake_db():
        yield SimpleNamespace(commit=lambda: None)

    seen = []
    out = an.collect("Testorg", channels, an.quick_config("Testorg", list(channels.values())),
                     lambda step, status, d: seen.append((step, status, dict(d))),
                     client=SimpleNamespace(quota_used=7), database=fake_db)
    comments = [d for step, status, d in seen if step == "comments" and status == "running"]
    assert comments[0]["channels_done"] == [ch3] and comments[0]["channel_now"] == CH1
    assert [CH1] == [c for c in comments[-1]["channels_done"] if c == CH1]
    assert comments[-1]["channels_done"] == [ch3, CH1, CH2] and comments[-1]["videos_done"] == 5
    assert out["comments"]["collected"] == 5 and out["snapshot_id"] == "rs-20990101T000000Z"
