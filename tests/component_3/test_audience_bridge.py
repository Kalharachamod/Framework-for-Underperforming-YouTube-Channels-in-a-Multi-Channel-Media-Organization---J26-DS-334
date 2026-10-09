"""Tests for the STEP 19 Audience Bridge Score (provisional formula).

TEST DATA (synthetic): the STEP 21 evaluation fixture (cricket channels A, B, C sharing commenters,
cooking channels D, E sharing commenters, F isolated, X without videos). Never real data.
"""

import json
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from research.component_3.model import audience_bridge as ab
from research.component_3.model import baselines as bl
from research.component_3.model import ppr_diffusion as ppr
from test_evaluation import CN, FakeEncoder, build_snapshot, ticking  # noqa: F401  (shared synthetic fixture)


@pytest.fixture
def sid(isolated_data_dir, ticking):  # noqa: F811
    return build_snapshot()


@pytest.fixture
def result(sid):
    return ab.run(sid, encoder=FakeEncoder())


def pair(r, a, b):
    s = r.scores
    return s[(s.source_channel_id == CN[a]) & (s.destination_channel_id == CN[b])].iloc[0]


def test_minmax_constant_and_null_handling():
    assert ab.minmax(pd.Series([1.0, 3.0, None])).tolist()[:2] == [0.0, 1.0]
    assert pd.isna(ab.minmax(pd.Series([1.0, 3.0, None])).iloc[2])
    assert ab.minmax(pd.Series([0.0, 0.0])).tolist() == [0.0, 0.0]          # no signal: a true zero
    assert ab.minmax(pd.Series([0.4, 0.4])).isna().all()                     # undefined, never invented


@pytest.mark.parametrize("kw", [{"w_diffusion": 0.7, "w_topic": 0.5}, {"w_diffusion": -0.1, "w_topic": 1.1},
                                {"confidence_k": 0}, {"normalization": "zscore"}])
def test_config_validation(kw):
    with pytest.raises(ab.BridgeError):
        ab.BridgeConfig(**kw)


def test_known_decomposition(result):
    ac = pair(result, "A", "C")
    assert ac.shared_commenters == 2 and ac.evidence_confidence == pytest.approx(2 / 5)
    assert ac.normalized_diffusion == pytest.approx(1.0) and ac.normalized_topic_similarity == pytest.approx(1.0)
    assert ac.base_score == pytest.approx(1.0) and ac.audience_bridge_score == pytest.approx(0.4)
    assert ac["rank"] == 1 and ac.score_status == "ok"
    ad = pair(result, "A", "D")
    assert ad.shared_commenters == 0 and ad.audience_bridge_score == 0.0      # observed zero overlap


def test_score_equals_base_times_confidence(result):
    ok = result.scores[result.scores.score_status == "ok"]
    np.testing.assert_allclose(ok.audience_bridge_score.astype(float),
                               ((ok.diffusion_contribution + ok.topic_contribution) * ok.confidence).astype(float))
    assert ok[["audience_bridge_score", "confidence", "base_score"]].astype(float).apply(lambda c: c.between(0, 1)).all().all()


def test_missing_components_are_incomplete_not_zero(result):
    ax = pair(result, "A", "X")      # X has no videos: no topic profile
    assert pd.isna(ax.audience_bridge_score) and pd.isna(ax["rank"]) and ax.score_status.startswith("incomplete")
    xa = pair(result, "X", "A")      # X cannot be a diffusion source
    assert "diffusion" in xa.score_status


def test_no_self_pairs_and_provenance(result, sid):
    s = result.scores
    assert (s.source_channel_id != s.destination_channel_id).all()
    assert set(s.snapshot_id) == {sid} and set(s.experiment_id) == {result.experiment_id}
    assert result.metadata["inputs"]["diffusion_experiment_id"].startswith("ppr-")
    assert result.metadata["inputs"]["topic_experiment_id"].startswith("top-")


def test_rejects_components_from_another_snapshot(sid):
    inp = bl.load_input(sid)
    other = build_snapshot(interactions=[("G1", "A1"), ("G1", "B1")])
    diff = ppr.run_diffusion(bl.load_input(other).graph)
    from research.component_3.model import topic_similarity as ts
    topic = ts.run(sid, as_of=inp.as_of, encoder=FakeEncoder())
    with pytest.raises(ab.BridgeError, match="different snapshots"):
        ab.score(inp, diff, topic)


def test_weights_change_scores_and_id(sid):
    a = ab.run(sid, encoder=FakeEncoder())
    b = ab.run(sid, ab.BridgeConfig(w_diffusion=1.0, w_topic=0.0), encoder=FakeEncoder())
    assert a.experiment_id != b.experiment_id
    assert pair(b, "A", "B").topic_contribution == 0.0


def test_deterministic_and_write_once(sid, result):
    again = ab.run(sid, encoder=FakeEncoder())
    assert again.experiment_id == result.experiment_id and again.scores.equals(result.scores)
    out = ab.save(result)
    assert ab.save(again) == out and ab.load(out).scores.equals(result.scores)
    meta = json.loads((out / ab.RUN_FILE).read_text(encoding="utf-8"))
    meta["scores_sha256"] = "0" * 64
    (out / ab.RUN_FILE).write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(ab.BridgeError, match="checksum"):
        ab.load(out)


def test_validation_detects_inconsistent_scores(result):
    bad = replace(result, scores=result.scores.assign(audience_bridge_score=result.scores.audience_bridge_score * 1.1))
    with pytest.raises(ab.BridgeError, match="base_score"):
        ab.validate(bad)


def test_cli(sid, monkeypatch, capsys):
    real = ab.run
    monkeypatch.setattr(ab, "run", lambda s, c, **kw: real(s, c, **{**kw, "encoder": FakeEncoder()}))
    assert ab.main(["--snapshot", sid]) == 0
    assert "provisional" in capsys.readouterr().out
    assert ab.main(["--snapshot", sid, "--w-diffusion", "1.5"]) == 1
