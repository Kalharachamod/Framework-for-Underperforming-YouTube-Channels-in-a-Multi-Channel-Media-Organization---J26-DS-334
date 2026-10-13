"""Tests for the STEP 22 explainability framework.

TEST DATA (synthetic): the STEP 21 evaluation fixture (cricket channels A, B, C sharing commenters,
cooking channels D, E sharing commenters, F isolated, X without videos). Synthetic outputs are
test checks only, not research findings.
"""

import json
from dataclasses import replace

import pandas as pd
import pytest

from research.component_3.evaluation import evaluate as ev
from research.component_3.explainability import evidence as evd
from research.component_3.explainability import explain as ex
from research.component_3.explainability import sensitivity as sens
from research.component_3.model import audience_bridge as ab
from research.component_3.model import baselines as bl
from test_evaluation import CN, P, RAW, SMALL_N2V, FakeEncoder, build_snapshot, ticking  # noqa: F401


@pytest.fixture
def sid(isolated_data_dir, ticking):  # noqa: F811
    return build_snapshot()


NO_EMB = ab.BridgeConfig(w_diffusion=0.5, w_embedding=0.0, w_topic=0.5, embedding_source="none")


@pytest.fixture
def bridge(sid):
    """Two-component configuration, so known values from STEP 19/22 can be asserted exactly."""
    return ab.run(sid, NO_EMB, encoder=FakeEncoder())


@pytest.fixture
def result(bridge):
    return ex.explain(bridge)


def row(table, a, b):
    return table[(table.source_channel_id == CN[a]) & (table.destination_channel_id == CN[b])].iloc[0]


# 1-3. decomposition, tolerance, missing components -------------------------------------------

def test_score_decomposition(result):
    x = row(result.tables["bridge_score_explanations"], "A", "C")
    assert x.explanation_status == "complete"
    assert x.diffusion_contribution == pytest.approx(x.w_diffusion * x.normalized_diffusion)
    assert x.topic_contribution == pytest.approx(x.w_topic * x.normalized_topic_similarity)
    assert x.base_score == pytest.approx(x.diffusion_contribution + x.topic_contribution)
    assert x.audience_bridge_score == pytest.approx(x.base_score * x.confidence) == pytest.approx(0.4)
    assert x.diffusion_share_of_base == pytest.approx(0.5) and x.reconstruction_error <= 1e-12
    assert "x confidence" in x.explanation_text


def test_reconstruction_tolerance(bridge):
    s = bridge.scores.copy()
    i = s.index[(s.source_channel_id == CN["A"]) & (s.destination_channel_id == CN["C"])][0]
    s.loc[i, "audience_bridge_score"] += 1e-6
    x = ex.explain(replace(bridge, scores=s)).tables["bridge_score_explanations"]
    assert row(x, "A", "C").explanation_status == "reconstruction_mismatch"
    loose = ex.explain(replace(bridge, scores=s), ex.ExplainConfig(reconstruction_tolerance=1e-5))
    assert row(loose.tables["bridge_score_explanations"], "A", "C").explanation_status == "complete"


def test_missing_components_are_incomplete(result):
    x = row(result.tables["bridge_score_explanations"], "A", "X")
    assert x.explanation_status == "incomplete" and pd.isna(x.diffusion_share_of_base)
    assert "insufficient_evidence" in x.reason_codes and "not decomposed" in x.uncertainty_notes


# 4-5. evidence ---------------------------------------------------------------------------------

def test_evidence_aggregation(result):
    e = row(result.tables["bridge_evidence_summaries"], "A", "C")
    assert (e.shared_commenters, e.shared_videos_on_source, e.shared_videos_on_destination) == (2, 2, 1)
    assert e.shared_comments_on_source == 2 and e.shared_comments_on_destination == 2
    assert e.jaccard_similarity == pytest.approx(0.5) and e.source_video_coverage == pytest.approx(1.0)
    assert e.shared_active_days == 4 and e.temporal_state == evd.OBSERVED


def test_zero_missing_and_insufficient_are_distinct(result):
    ev_ = result.tables["bridge_evidence_summaries"]
    zero, insuff = row(ev_, "A", "D"), row(ev_, "A", "X")
    assert zero.shared_commenter_state == evd.ZERO and zero.shared_commenters == 0
    assert insuff.shared_commenter_state == evd.INSUFFICIENT and pd.isna(insuff.shared_commenters)
    assert insuff.topic_state == evd.MISSING and zero.topic_state == evd.OBSERVED


# 6-8. reasons and criteria ------------------------------------------------------------------------

def test_confidence_interpretation(bridge, sid):
    x = result_codes(ex.explain(bridge), "A", "C")
    assert "low_confidence_sparse_evidence" in x and "strong_shared_commenter_evidence" not in x
    strong = ab.run(sid, replace(NO_EMB, confidence_k=2.0), encoder=FakeEncoder())
    assert "strong_shared_commenter_evidence" in result_codes(ex.explain(strong), "A", "C")
    assert "no_shared_commenter_evidence" in result_codes(ex.explain(bridge), "A", "D")


def result_codes(r, a, b):
    return row(r.tables["bridge_score_explanations"], a, b).reason_codes.split(";")


def test_reason_selection(result):
    codes = result_codes(result, "A", "C")
    assert {"strong_structural_connectivity", "high_topic_similarity"} <= set(codes)
    assert "broad_video_coverage" not in codes and "consistent_temporal_support" not in codes   # disabled
    rs = result.tables["bridge_explanation_reasons"]
    r = rs[(rs.source_channel_id == CN["A"]) & (rs.destination_channel_id == CN["C"]) &
           (rs.reason_code == "low_confidence_sparse_evidence")].iloc[0]
    assert r.value == 2 and r.threshold == 3 and "confidence_k" in r.criterion


def test_configurable_criteria(bridge):
    cfg = ex.ExplainConfig(broad_video_coverage=0.5, consistent_temporal_active_days=3)
    r = ex.explain(bridge, cfg)
    codes = result_codes(r, "A", "C")
    assert "broad_video_coverage" in codes and "consistent_temporal_support" in codes
    assert r.metadata["explanation_config_id"] != ex.ExplainConfig().config_id()
    narrow = ex.explain(bridge, ex.ExplainConfig(strong_relative_fraction=0.01))
    assert "strong_structural_connectivity" in result_codes(narrow, "A", "C")       # rank 1 always within ceil()
    assert "strong_structural_connectivity" not in result_codes(narrow, "A", "B")
    with pytest.raises(ex.ExplainError):
        ex.ExplainConfig(strong_relative_fraction=0)


# 9-11. ranking context, incompatible inputs, self pairs -------------------------------------------

def test_ranking_context(result):
    x = result.tables["bridge_score_explanations"]
    ab_ = row(x, "A", "B")
    assert ab_["rank"] == 2 and ab_.candidate_destinations == 6 and ab_.scored_destinations == 5
    assert ab_.next_higher_destination == CN["C"] and ab_.next_higher_score == pytest.approx(0.4)
    comp = json.loads(ab_.top_competitors)
    assert comp[0]["destination_channel_id"] == CN["C"] and all(c["destination_channel_id"] != CN["B"] for c in comp)


def test_incompatible_snapshots_rejected(bridge, sid):
    other = build_snapshot(interactions=[("G1", "A1"), ("G1", "B1")])
    with pytest.raises(ex.ExplainError, match="differs"):
        ex.explain(bridge, inp=bl.load_input(other))
    mixed = bridge.scores.copy()
    mixed.loc[0, "experiment_id"] = "abs-other"
    with pytest.raises(ex.ExplainError, match="incompatible"):
        ex.explain(replace(bridge, scores=mixed))


def test_self_channel_pairs_excluded(bridge):
    self_row = bridge.scores.iloc[[0]].assign(destination_channel_id=bridge.scores.source_channel_id.iloc[0])
    r = ex.explain(replace(bridge, scores=pd.concat([bridge.scores, self_row], ignore_index=True)))
    for name in ("bridge_score_explanations", "bridge_evidence_summaries", "bridge_sensitivity_results"):
        t = r.tables[name]
        assert (t.source_channel_id != t.destination_channel_id).all()


# 12-13. sensitivity --------------------------------------------------------------------------

def test_sensitivity_component_removal(result):
    s = result.tables["bridge_sensitivity_results"]
    orig = s[s.scenario == "original"]
    assert (orig.score_delta.dropna().abs() < 1e-12).all() and (orig.rank_change.dropna() == 0).all()
    nd = s[(s.scenario == "diffusion_removed") & (s.source_channel_id == CN["A"]) &
           (s.destination_channel_id == CN["C"])].iloc[0]
    assert nd.scenario_score == pytest.approx(0.2) and nd.score_delta == pytest.approx(-0.2)
    nc = s[(s.scenario == "confidence_removed") & (s.source_channel_id == CN["A"]) &
           (s.destination_channel_id == CN["C"])].iloc[0]
    assert nc.scenario_score == pytest.approx(1.0)
    assert set(s[s.status != "ok"].scenario_score.isna()) == {True}


def test_alternative_weights_sum_to_one(bridge, result):
    for sc in sens.scenarios((0.5, 0.0, 0.5), ex.ExplainConfig().alternative_weights):
        assert sum(sc["weights"].values()) == pytest.approx(1.0)
    names = set(result.tables["bridge_sensitivity_results"].scenario)
    assert {"weights_d0_e0_t1", "weights_d1_e0_t0"} <= names and "embedding_removed" not in names   # w_e = 0
    emb_only = result.tables["bridge_sensitivity_results"]
    assert set(emb_only[emb_only.scenario == "weights_d0_e1_t0"].status) == {
        "not_computed: a required component is not stored", "not_computed: incomplete score components"}
    with pytest.raises(ValueError):
        sens.scenarios((0.5, 0.0, 0.5), ((1.5, 0.0, 0.0),))
    assert bridge.scores.equals(ab.run(bridge.snapshot_id, NO_EMB, encoder=FakeEncoder()).scores)   # untouched


# 14-18. determinism, privacy, temporal, sparse, provenance ----------------------------------------

def test_deterministic_outputs(bridge):
    a, b = ex.explain(bridge), ex.explain(bridge)
    assert a.explanation_id == b.explanation_id
    for n in a.tables:
        assert ex.digest(a.tables[n].drop(columns=["created_at"], errors="ignore")) == \
            ex.digest(b.tables[n].drop(columns=["created_at"], errors="ignore"))
    out = ex.save(a)
    assert ex.save(b) == out and set(ex.load(out).tables) == set(a.tables)


def test_no_raw_or_hashed_commenter_ids(result):
    blob = "".join(t.to_csv() for t in result.tables.values()) + json.dumps(result.metadata, default=str)
    assert not any(v in blob for v in RAW.values()) and not any(v in blob for v in P.values())
    assert "anon_" not in blob
    bad = result.tables["bridge_score_explanations"].copy()
    bad.loc[0, "uncertainty_notes"] = P["G1"]
    with pytest.raises(ex.ExplainError, match="commenter identifiers"):
        ex.validate(replace(result, tables={**result.tables, "bridge_score_explanations": bad}), ex.ExplainConfig())


def test_insufficient_temporal_evidence(isolated_data_dir, ticking):  # noqa: F811
    one_day = [("G1", "A1"), ("G1", "B1")]                 # comments k0, k1 -> days 02 and 03
    sid = build_snapshot(interactions=one_day)
    r = ex.explain(ab.run(sid, encoder=FakeEncoder()), ex.ExplainConfig(min_temporal_active_days=3))
    x = row(r.tables["bridge_score_explanations"], "A", "B")
    assert "insufficient_temporal_evidence" in x.reason_codes
    e = row(r.tables["bridge_evidence_summaries"], "A", "C")
    assert e.temporal_state == evd.INSUFFICIENT                             # C has no commenters at all


def test_sparse_graph_without_comments(isolated_data_dir, ticking):  # noqa: F811
    sid = build_snapshot(interactions=[])
    r = ex.explain(ab.run(sid, encoder=FakeEncoder()))
    ev_ = r.tables["bridge_evidence_summaries"]
    assert set(ev_.shared_commenter_state) == {evd.INSUFFICIENT}
    assert r.metadata["validation"]["passed"]


def test_empty_score_table(bridge):
    empty = replace(bridge, scores=bridge.scores.iloc[0:0])
    r = ex.explain(empty)
    assert all(len(t) == 0 for t in r.tables.values())


def test_provenance(result, bridge, sid):
    for name, t in result.tables.items():
        assert set(t.snapshot_id) == {sid}, name
        assert set(t.experiment_id) == {bridge.experiment_id}, name
        assert set(t.explanation_config_id) == {ex.ExplainConfig().config_id()}, name
    assert result.metadata["scoring_inputs"]["diffusion_experiment_id"].startswith("ppr-")


# 19. integration with STEP 19-21 -------------------------------------------------------------

def test_integration_with_evaluation(sid):
    bridge = ab.run(sid, encoder=FakeEncoder())          # default configuration, as evaluated by STEP 21
    before = ex.explain(bridge).metadata["evaluation_context"]
    assert before["evaluations_of_this_experiment"] == [] and "not an empirical evaluation" in before["note"]
    r = ev.evaluate(sid, ev.EvaluationConfig(run_sparse=False, run_temporal=False), encoder=FakeEncoder(),
                    node2vec_config=SMALL_N2V)
    assert r.metadata["methods"]["audience_bridge_score"]["experiment_id"] == bridge.experiment_id
    ev.save(r)
    after = ex.explain(bridge).metadata["evaluation_context"]
    assert after["evaluations_of_this_experiment"][0]["evaluation_id"] == r.evaluation_id
    assert after["abs_labelled_evaluation"] is False


def test_cli(sid, bridge, capsys):
    assert ex.main(["--snapshot", sid]) == 1                                # no saved bridge run yet
    ab.save(bridge)
    assert ex.main(["--snapshot", sid]) == 0
    out = capsys.readouterr().out
    assert "not empirical validation" in out and "rank 1" in out


# --- three-component score (default configuration) -------------------------------------------

def test_explanations_with_embedding_component(sid):
    r = ex.explain(ab.run(sid, encoder=FakeEncoder()))
    x = row(r.tables["bridge_score_explanations"], "A", "C")
    assert x.explanation_status == "complete" and x.reconstruction_error <= 1e-12
    assert x.w_embedding == pytest.approx(1 / 3) and x.embedding_source == "metapath2vec"
    assert x.base_score == pytest.approx(x.diffusion_contribution + x.embedding_contribution + x.topic_contribution)
    assert x.diffusion_share_of_base + x.embedding_share_of_base + x.topic_share_of_base == pytest.approx(1.0)
    assert "embedding" in x.explanation_text and "[metapath2vec]" in x.explanation_text
    e = row(r.tables["bridge_evidence_summaries"], "A", "C")
    assert e.embedding_state == evd.OBSERVED and -1 <= e.embedding_similarity <= 1
    assert row(r.tables["bridge_evidence_summaries"], "A", "X").embedding_state == evd.MISSING
    s = r.tables["bridge_sensitivity_results"]
    assert {"embedding_removed", "diffusion_removed", "topic_removed"} <= set(s.scenario)
    assert (s[(s.scenario == "original") & (s.status == "ok")].score_delta.abs() < 1e-12).all()
    removed = s[(s.scenario == "embedding_removed") & (s.source_channel_id == CN["A"]) & (s.destination_channel_id == CN["C"])]
    assert removed.scenario_score.iloc[0] == pytest.approx((x.diffusion_contribution + x.topic_contribution) * x.confidence)


def test_embedding_reason_is_relative_and_configurable(sid):
    r = ex.explain(ab.run(sid, encoder=FakeEncoder()))
    reasons = r.tables["bridge_explanation_reasons"]
    emb = reasons[reasons.reason_code == "strong_embedding_similarity"]
    assert len(emb) > 0 and (emb.criterion.str.contains("per-source rank")).all()
    none = ex.explain(ab.run(sid, NO_EMB, encoder=FakeEncoder())).tables["bridge_explanation_reasons"]
    assert "strong_embedding_similarity" not in set(none.reason_code)
    assert set(ex.explain(ab.run(sid, NO_EMB, encoder=FakeEncoder())).tables["bridge_evidence_summaries"]
               .embedding_state) == {evd.NOT_USED}
