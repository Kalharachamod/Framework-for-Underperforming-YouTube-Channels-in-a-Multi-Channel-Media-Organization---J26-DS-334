"""Tests for the Component 3 evaluation framework (STEP 21).

TEST DATA (synthetic): channels A, B, C share commenters (cricket videos), D, E share commenters
(cooking videos), F has its own commenter only, X has no videos. Built through the real
STEP 12 -> 13 -> 14 pipeline. Pseudonyms from a test salt. Never real data, never the network.
"""

import json
import sys
import types
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from research.component_3.evaluation import analysis as an
from research.component_3.evaluation import evaluate as ev
from research.component_3.evaluation import methods as me
from research.component_3.evaluation import metrics as mt
from research.component_3.evaluation import robustness as rb
from research.component_3.evaluation import temporal as tp
from research.component_3.model import baselines as bl
from research.component_3.model import topic_similarity as ts
from shared.schemas import Channel, Comment, Video, to_dataframe
from shared.utils import privacy
from shared.utils import snapshots as s

T = datetime(2026, 9, 30, 8, 0, tzinfo=timezone.utc)
SALT = b"test-salt-" + b"0" * 54
WHO = ["G1", "G2", "G3", "G4", "H1", "H2", "H3", "F1"]
RAW = {k: f"UC_raw_eval_{k}_xxxxxxx" for k in WHO}
P = {k: privacy.pseudonymize_id(v, SALT) for k, v in RAW.items()}
CH = {k: f"UC_test_{k}" for k in "ABCDEFX"}
CN = {k: f"channel:{v}" for k, v in CH.items()}
VIDEOS = {"A1": "A", "A2": "A", "B1": "B", "C1": "C", "D1": "D", "E1": "E", "F1v": "F"}
TITLES = {"A": "Cricket highlights", "B": "Cricket match", "C": "Cricket news", "D": "Cooking rice",
          "E": "Cooking curry", "F": "Cooking cake"}
INTERACTIONS = [("G1", "A1"), ("G1", "B1"), ("G2", "B1"), ("G2", "C1"), ("G3", "A2"), ("G3", "C1"),
                ("G4", "A1"), ("G4", "B1"), ("G4", "C1"), ("H1", "D1"), ("H1", "E1"), ("H2", "D1"),
                ("H2", "E1"), ("H3", "E1"), ("H3", "D1"), ("F1", "F1v")]
SMALL_N2V = bl.Node2VecConfig(dimensions=8, walk_length=10, walks_per_node=3, window=2, negative=2, epochs=2, seed=5)
FAST = ev.EvaluationConfig(sparse_fractions=(0.5,), sparse_seeds=(0, 1))


class FakeEncoder:
    """Known vectors by keyword: cricket -> [1, 0], cooking -> [0, 1]."""

    name, version = "fake_keyword_encoder", "test"

    def encode(self, texts):
        return np.array([[1.0, 0.0] if "ricket" in t else [0.0, 1.0] if "ooking" in t else [0.6, 0.8]
                         for t in texts], dtype=float).reshape(len(texts), 2)


def build_snapshot(interactions=INTERACTIONS, videos=None, extracted=datetime(2026, 10, 1, tzinfo=timezone.utc)):
    videos = videos if videos is not None else VIDEOS
    chans = [Channel(channel_id=CH[k], channel_name=k, collected_at=T) for k in "ABCDEFX"]
    vids = [Video(video_id=v, channel_id=CH[c], title=f"{TITLES[c]} {v}", published_at="2026-09-01T00:00:00Z",
                  collected_at=T) for v, c in videos.items()]
    comms = [Comment(comment_id=f"k{i}", video_id=v, channel_id=CH[videos[v]], author_channel_id=P[w],
                     comment_text="Synthetic.", published_at=f"2026-09-{(i % 25) + 2:02d}T10:00:00Z", collected_at=T)
             for i, (w, v) in enumerate(interactions)]
    frames = {"channels": to_dataframe(chans, Channel), "videos": to_dataframe(vids, Video),
              "comments": to_dataframe(comms, Comment)}
    return s.create_research_snapshot(frames, source="synthetic_test", extracted_at=extracted).snapshot_id


@pytest.fixture
def ticking(monkeypatch):
    times = iter(datetime(2026, 10, 9, 10, 0, tzinfo=timezone.utc) + timedelta(seconds=i) for i in range(2000))
    monkeypatch.setattr(s, "_utcnow", lambda: next(times))


@pytest.fixture
def sid(isolated_data_dir, ticking):
    return build_snapshot()


@pytest.fixture
def ctx(sid):
    return me.MethodContext(sid, bl.load_input(sid), encoder=FakeEncoder(), node2vec_config=SMALL_N2V)


def run_eval(sid, config=FAST, **kw):
    return ev.evaluate(sid, config, encoder=FakeEncoder(), node2vec_config=SMALL_N2V, **kw)


def rows(table, **eq):
    out = table
    for k, v in eq.items():
        out = out[out[k] == v]
    return out


# --- metrics --------------------------------------------------------------------------------

def test_relevance_metrics_known_values():
    ranked = ["a", "b", "c", "d"]
    assert mt.precision_at_k(ranked, {"b", "d"}, 2) == 0.5
    assert mt.recall_at_k(ranked, {"b", "d"}, 2) == 0.5
    assert mt.reciprocal_rank(ranked, {"c"}) == pytest.approx(1 / 3)
    assert mt.reciprocal_rank(ranked, {"z"}) == 0.0
    ideal = 2 / np.log2(2) + 1 / np.log2(3)
    assert mt.ndcg_at_k(ranked, {"a": 2, "b": 1}, 2) == pytest.approx(1.0)
    assert mt.ndcg_at_k(["b", "a"], {"a": 2, "b": 1}, 2) == pytest.approx((1 + 2 / np.log2(3)) / ideal)


def test_undefined_metrics_are_none_not_zero():
    assert mt.recall_at_k(["a"], set(), 1) is None
    assert mt.reciprocal_rank(["a"], set()) is None
    assert mt.ndcg_at_k(["a"], {"a": 0.0}, 1) is None
    assert mt.precision_at_k([], {"a"}, 3) is None
    assert mt.topk_jaccard([], [], 3) is None
    for bad in (0, -1, 1.5, True):
        with pytest.raises(ValueError):
            mt.precision_at_k(["a"], {"a"}, bad)
    with pytest.raises(ValueError):
        mt.ndcg_at_k(["a"], {"a": -1.0}, 1)


def test_rank_correlation_ties_nulls_and_edge_cases():
    a = {"x": 1.0, "y": 2.0, "z": 3.0, "w": None}
    v, n, why = mt.rank_correlation(a, {"x": 10.0, "y": 20.0, "z": 30.0, "w": 5.0})
    assert v == pytest.approx(1.0) and n == 3 and why is None          # NULL score excluded, not treated as 0
    v, _, _ = mt.rank_correlation(a, {"x": 3.0, "y": 2.0, "z": 1.0}, "kendall")
    assert v == pytest.approx(-1.0)
    assert mt.rank_correlation({"x": 1, "y": 2}, {"x": 1, "y": 2})[0] is None
    v, _, why = mt.rank_correlation({"x": 1, "y": 1, "z": 1}, {"x": 1, "y": 2, "z": 3})
    assert v is None and "constant" in why
    tied, _, _ = mt.rank_correlation({"x": 1, "y": 1, "z": 0, "q": 0}, {"x": 0.9, "y": 0.8, "z": 0.2, "q": 0.1})
    assert 0 < tied < 1                                                   # binary (tied) vs graded is defined
    assert mt.topk_jaccard(["a", "b"], ["b", "c"], 2) == pytest.approx(1 / 3)


# --- method adapters ------------------------------------------------------------------------

def test_standardize_ranks_ties_nulls_and_self_pairs():
    raw = pd.DataFrame({"source_channel_id": ["c:A"] * 4 + ["c:B"],
                        "destination_channel_id": ["c:A", "c:C", "c:B", "c:D", "c:A"],
                        "s": [9.0, 0.5, 0.5, None, 0.1]})
    df = me.standardize(raw, method="m", role="baseline", signal_type="graded", score_col="s", snapshot_id="rs",
                        experiment_id="e", channels=["c:A", "c:B", "c:C", "c:D"])
    assert list(df.columns) == me.RANKING_COLUMNS
    a = df[df.source_channel_id == "c:A"]
    assert "c:A" not in set(a.destination_channel_id)                     # self pair removed
    assert a.destination_channel_id.tolist() == ["c:B", "c:C", "c:D"]     # tie broken by destination id
    assert a["rank"].tolist()[:2] == [1, 2] and pd.isna(a["rank"].iloc[2])  # NULL score -> no rank
    assert a.tied.tolist() == [True, True, False]
    assert me.validate_rankings(df) == []
    bad = pd.concat([df, df.iloc[[0]]])
    assert "duplicate (source, destination) pairs" in me.validate_rankings(bad)


@pytest.mark.parametrize("method", ["ppr_diffusion", "topic_similarity", "louvain", "node2vec"])
def test_method_adapters_produce_valid_rankings(ctx, method):
    r = me.run_method(method, ctx)
    assert r.status == "ok" and r.experiment_id
    assert me.validate_rankings(r.rankings) == []
    assert set(r.rankings.source_channel_id) | set(r.rankings.destination_channel_id) <= set(ctx.baseline_input.channels)
    assert r.seconds >= 0 and r.python_peak_mib >= 0


def test_topic_and_louvain_signals_are_as_expected(ctx):
    topic = me.run_method("topic_similarity", ctx).rankings
    top_a = topic[(topic.source_channel_id == CN["A"]) & (topic["rank"] <= 2)]
    assert set(top_a.destination_channel_id) == {CN["B"], CN["C"]}
    lv = me.run_method("louvain", ctx).rankings
    assert set(lv.score.dropna()) <= {0.0, 1.0}


@pytest.fixture
def no_abs(monkeypatch):
    """Simulate a checkout without the STEP 19 module."""
    monkeypatch.setattr(me, "ABS_MODULE", "research.component_3.model._absent_abs_module")


def test_abs_slot_unavailable_without_step19(ctx, no_abs):
    r = me.run_method("audience_bridge_score", ctx)
    assert r.status == "unavailable" and "STEP 19" in r.reason
    assert r.rankings.empty and r.experiment_id is None


def test_abs_slot_runs_step19(ctx):
    r = me.run_method("audience_bridge_score", ctx)
    assert r.status == "ok" and r.experiment_id.startswith("abs-") and me.validate_rankings(r.rankings) == []
    assert r.rankings.role.iloc[0] == "proposed method"


def test_abs_slot_uses_step19_module_when_present(ctx, monkeypatch):
    mod = types.ModuleType(me.ABS_MODULE)

    def score_channels(c):   # test stand-in only: NOT a proposed formula
        ch = c.baseline_input.channels
        pairs = [(a, b) for a in ch for b in ch if a != b]
        return pd.DataFrame({"source_channel_id": [a for a, _ in pairs], "destination_channel_id": [b for _, b in pairs],
                             "audience_bridge_score": np.linspace(0, 1, len(pairs))}), "abs-test"

    mod.score_channels = score_channels
    monkeypatch.setitem(sys.modules, me.ABS_MODULE, mod)
    r = me.run_method("audience_bridge_score", ctx)
    assert r.status == "ok" and r.experiment_id == "abs-test" and me.validate_rankings(r.rankings) == []


def test_unknown_method_rejected(ctx):
    with pytest.raises(ValueError):
        me.run_method("magic", ctx)
    with pytest.raises(an.EvaluationError):
        ev.EvaluationConfig(methods=("magic",))


# --- labels and ranking quality -------------------------------------------------------------

def test_labels_are_validated(ctx):
    ch = ctx.baseline_input.channels
    ok = pd.DataFrame({"source_channel_id": [CN["A"]], "destination_channel_id": [CN["B"]], "relevance": [1],
                       "label_source": ["manual review"]})
    assert len(an.validate_labels(ok, ch)) == 1
    for change, msg in [({"label_source": [""]}, "label_source"), ({"relevance": [-1]}, "non-negative"),
                        ({"destination_channel_id": [CN["A"]]}, "self pairs"),
                        ({"destination_channel_id": ["channel:UC_unknown"]}, "not in the snapshot")]:
        with pytest.raises(an.EvaluationError, match=msg):
            an.validate_labels(ok.assign(**change), ch)
    with pytest.raises(an.EvaluationError, match="duplicate"):
        an.validate_labels(pd.concat([ok, ok]), ch)
    with pytest.raises(an.EvaluationError, match="missing column"):
        an.validate_labels(ok.drop(columns="label_source"), ch)


def test_no_labels_means_no_relevance_metrics(sid):
    r = run_eval(sid, ev.EvaluationConfig(run_sparse=False))
    rel = rows(r.tables["ranking_evaluation_results"], analysis="relevance")
    assert set(rel.status) == {"not_computed"} and rel.value.isna().all()
    assert len(rows(r.tables["ranking_evaluation_results"], analysis="agreement")) > 0
    assert r.metadata["labels"]["status"] == "none supplied"


def test_relevance_metrics_with_explicit_labels(sid, tmp_path):
    labels = pd.DataFrame({"source_channel_id": [CN["A"], CN["A"], CN["D"]],
                           "destination_channel_id": [CN["B"], CN["C"], CN["E"]],
                           "relevance": [2, 1, 1], "label_source": ["synthetic test judgement"] * 3})
    path = tmp_path / "labels.csv"
    labels.to_csv(path, index=False)
    r = run_eval(sid, ev.EvaluationConfig(labels_path=str(path), run_sparse=False, run_temporal=False))
    rel = rows(r.tables["ranking_evaluation_results"], analysis="relevance", method="topic_similarity")
    p1 = rows(rel, metric="precision_at_k", k=1).iloc[0]
    assert p1.value == pytest.approx(1.0) and p1.n_sources == 2
    assert rows(rel, metric="mrr").iloc[0].value == pytest.approx(1.0)
    assert r.metadata["labels"]["rows"] == 3 and len(r.metadata["labels"]["sha256"]) == 64


# --- agreement and top-k ----------------------------------------------------------------------

def test_identical_rankings_agree_perfectly(ctx):
    rk = me.run_method("ppr_diffusion", ctx).rankings
    res = {(x["metric"], x["k"]): x["value"] for x in an.compare_rankings(rk, rk, [1, 3])}
    assert res[("spearman", None)] == pytest.approx(1.0) and res[("topk_jaccard", 3)] == pytest.approx(1.0)


def test_top_k_table_and_boundary_ties():
    rk = me.standardize(pd.DataFrame({"source_channel_id": ["A"] * 3, "destination_channel_id": ["B", "C", "D"],
                                      "s": [0.9, 0.5, 0.5]}), method="m", role="r", signal_type="g", score_col="s",
                        snapshot_id="rs", experiment_id="e", channels=["A", "B", "C", "D"])
    tk = an.top_k_table(rk, [1, 2])
    assert tk["rank"].tolist() == [1, 2] and (tk.source_channel_id != tk.destination_channel_id).all()
    assert pd.isna(tk.boundary_tie_at_k.iloc[0]) and tk.boundary_tie_at_k.iloc[1] == "2"  # C (rank 2) ties with D just outside k=2
    summ = {(x["metric"], x["k"]): x["value"] for x in an.top_k_summary(rk, [1, 2])}
    assert summ[("topk_boundary_tie_share", 2)] == 1.0 and summ[("topk_boundary_tie_share", 1)] == 0.0


# --- temporal stability -----------------------------------------------------------------------

def test_single_snapshot_is_insufficient_temporal_data(sid):
    r = run_eval(sid, ev.EvaluationConfig(run_sparse=False))
    t = r.tables["temporal_stability_results"]
    assert set(t.status) == {tp.INSUFFICIENT} and t.value.isna().all()
    assert r.metadata["temporal"]["status"] == tp.INSUFFICIENT


def test_different_observation_windows_are_not_compared(isolated_data_dir, ticking):
    first = build_snapshot(videos={"A1": "A", "B1": "B", "C1": "C", "D1": "D", "E1": "E", "F1v": "F"},
                           interactions=[(w, v) for w, v in INTERACTIONS if v != "A2"])
    deep = {**VIDEOS, **{f"{c}{i}x": c for c in "ABCDEF" for i in range(4)}}
    second = build_snapshot(videos=deep, extracted=datetime(2026, 10, 2, tzinfo=timezone.utc))
    r = run_eval(second, ev.EvaluationConfig(run_sparse=False))
    t = r.tables["temporal_stability_results"]
    assert set(t.status) <= {tp.INSUFFICIENT, "not_comparable"} and t.value.isna().all()
    assert "different observation windows" in r.metadata["temporal"]["pairs"][0]["reason"]


def test_comparable_snapshots_are_scored(isolated_data_dir, ticking):
    first = build_snapshot(interactions=INTERACTIONS[:-2])
    second = build_snapshot(extracted=datetime(2026, 10, 2, tzinfo=timezone.utc))
    r = run_eval(second, ev.EvaluationConfig(run_sparse=False, methods=("ppr_diffusion", "louvain")))
    t = r.tables["temporal_stability_results"]
    ok = rows(t, status="ok")
    assert len(ok) > 0 and set(ok.earlier_snapshot_id) == {first} and set(ok.later_snapshot_id) == {second}
    assert rows(ok, method="ppr_diffusion", metric="spearman").iloc[0].value <= 1.0
    assert r.metadata["temporal"]["comparable_pairs"] == 1


def test_identical_data_is_not_a_temporal_change(isolated_data_dir, ticking):
    a = build_snapshot()
    b = build_snapshot(extracted=datetime(2026, 10, 2, tzinfo=timezone.utc))
    _, pairs = tp.plan([a, b])
    assert pairs[0]["comparable"] is False and "identical data" in pairs[0]["reason"]


# --- sparse robustness ----------------------------------------------------------------------

def test_subsample_is_seeded_and_bounded(sid):
    c = rb.read_frames(sid)["comments"]
    a, b = rb.subsample(c, 0.5, 7), rb.subsample(c, 0.5, 7)
    assert a.equals(b) and len(a) == 8
    assert not a.equals(rb.subsample(c, 0.5, 8))
    by_user = rb.subsample(c, 0.5, 7, "commenters")
    assert by_user.author_channel_id.nunique() == 4
    with pytest.raises(ValueError):
        rb.subsample(c, 0.0, 1)


def test_sparse_simulation_never_touches_production_data(sid, no_abs):
    before = [(x.snapshot_id, x.manifest["datasets"]["comments"]["sha256"]) for x in s.list_research_snapshots()]
    r = run_eval(sid, ev.EvaluationConfig(run_temporal=False, sparse_fractions=(1.0, 0.5), sparse_seeds=(0,)))
    after = [(x.snapshot_id, x.manifest["datasets"]["comments"]["sha256"]) for x in s.list_research_snapshots()]
    assert before == after and s.verify_research_snapshot(sid).ok
    sp = r.tables["sparse_robustness_results"]
    full = rows(sp, method="ppr_diffusion", metric="spearman", retain_fraction=1.0)
    assert full.iloc[0].value == pytest.approx(1.0)                      # same data -> same ranking
    half = rows(sp, method="ppr_diffusion", retain_fraction=0.5)
    assert set(half.simulated_comments) == {8}
    assert "topic_similarity" not in set(sp.method)
    assert "topic_similarity" in r.metadata["sparse_robustness"]["unchanged_by_design"]
    assert set(rows(sp, method="audience_bridge_score").status) == {"unavailable"}


def test_sparse_results_are_reproducible(sid):
    a = run_eval(sid, ev.EvaluationConfig(run_temporal=False, sparse_fractions=(0.5,), sparse_seeds=(3,)))
    b = run_eval(sid, ev.EvaluationConfig(run_temporal=False, sparse_fractions=(0.5,), sparse_seeds=(3,)))
    cols = [c for c in rb.ROBUSTNESS_COLUMNS if c != "simulated_snapshot_id"]
    pd.testing.assert_frame_equal(a.tables["sparse_robustness_results"][cols],
                                  b.tables["sparse_robustness_results"][cols])


# --- performance, artifacts, metadata -----------------------------------------------------------

def test_performance_is_measured_not_estimated(sid, no_abs):
    r = run_eval(sid)
    perf = r.tables["computational_performance_results"]
    main = rows(perf, stage="main")
    assert (main[main.status == "ok"].seconds >= 0).all()
    unavailable = rows(main, method="audience_bridge_score").iloc[0]
    assert unavailable.status == "unavailable" and pd.isna(unavailable.seconds)
    assert set(perf.stage) >= {"main", "sparse_simulation"}
    assert "tracemalloc" in r.metadata["performance"]["memory_note"]


def test_full_run_metadata_and_abs_note(sid, no_abs):
    r = run_eval(sid)
    m = r.metadata
    assert r.evaluation_id.startswith("eval-") and m["validation"]["passed"]
    assert m["proposed_method"]["status"] == "unavailable" and "not yet available" in m["proposed_method"]["note"]
    assert m["methods"]["louvain"]["role"] == "baseline"
    assert m["methods"]["ppr_diffusion"]["role"] == "component of proposed method"
    assert m["as_of"] == "2026-10-01T00:00:00Z"                           # leakage control: snapshot time
    for df in r.tables.values():
        assert (df.snapshot_id == sid).all() and (df.evaluation_id == r.evaluation_id).all()


def test_evaluation_id_is_deterministic(sid):
    cfg = ev.EvaluationConfig(run_sparse=False, run_temporal=False)
    a, b = run_eval(sid, cfg), run_eval(sid, cfg)
    assert a.evaluation_id == b.evaluation_id
    assert run_eval(sid, ev.EvaluationConfig(run_sparse=False, run_temporal=False, ks=(2,))).evaluation_id != \
        a.evaluation_id


def test_save_write_once_and_load(sid):
    cfg = ev.EvaluationConfig(sparse_fractions=(0.5,), sparse_seeds=(0,))
    r = run_eval(sid, cfg)
    out = ev.save(r)
    names = {p.name for p in out.iterdir()}
    assert names == {f"{n}.parquet" for n in r.tables} | {ev.METADATA_FILE}
    assert ev.save(run_eval(sid, cfg)) == out                          # identical results (timings aside) accepted
    loaded = ev.load(out)
    for n in ev.DETERMINISTIC_TABLES:
        assert ev.digest(loaded.tables[n]) == ev.digest(r.tables[n])
    meta = json.loads((out / ev.METADATA_FILE).read_text(encoding="utf-8"))
    meta["table_sha256"]["top_k_evaluation_results"] = "0" * 64
    (out / ev.METADATA_FILE).write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(an.EvaluationError, match="checksum"):
        ev.load(out)


def test_outputs_contain_no_raw_commenter_ids(sid):
    r = run_eval(sid)
    blob = "".join(df.to_csv() for df in r.tables.values()) + json.dumps(r.metadata, default=str)
    assert not any(raw in blob for raw in RAW.values())


def test_validation_rejects_bad_values(sid):
    r = run_eval(sid, ev.EvaluationConfig(run_sparse=False, run_temporal=False))
    t = r.tables["ranking_evaluation_results"].copy()
    t.loc[t.index[t.status == "ok"][0], "value"] = pd.NA
    r.tables["ranking_evaluation_results"] = t
    with pytest.raises(an.EvaluationError, match="status is ok"):
        ev.validate(r)


def test_cli(sid, monkeypatch, capsys, no_abs):
    real = ev.evaluate
    monkeypatch.setattr(ev, "evaluate", lambda s_, c, **kw: real(s_, c, **{**kw, "encoder": FakeEncoder(),
                                                                           "node2vec_config": SMALL_N2V}))
    assert ev.main(["--snapshot", sid, "--skip-sparse"]) == 0
    out = capsys.readouterr().out
    assert "not yet available" in out and "spearman" in out
    assert ev.main(["--snapshot", sid, "--labels", "missing.csv"]) == 1


def test_full_run_with_step19_scores(sid):
    r = run_eval(sid, ev.EvaluationConfig(run_sparse=False, run_temporal=False))
    assert r.metadata["proposed_method"]["status"] == "ok" and r.metadata["proposed_method"]["note"] is None
    agree = rows(r.tables["ranking_evaluation_results"], analysis="agreement", method="audience_bridge_score")
    assert set(agree.reference_method) == {"ppr_diffusion", "topic_similarity", "metapath2vec_similarity",
                                         "hgt_similarity", "louvain", "node2vec"}
