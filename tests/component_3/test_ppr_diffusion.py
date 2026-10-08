"""Tests for Personalized PageRank diffusion (Component 3).

TEST DATA (synthetic) - the specification's chain plus an isolated part:
  A1 (channel A) <- P1 -> B1 (channel B);  B2 (channel B) <- P2 -> C1 (channel C)
  D1 (channel D) <- P3  (no shared commenter: D is disconnected from A, B, C)
  channel E has no videos (dangling)
Built through the real STEP 12 -> 13 pipeline; pseudonyms from a test salt.
"""

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from research.component_3.model import ppr_diffusion as ppr
from research.component_3.preprocessing import hetero_graph as hg
from shared.schemas import Channel, Comment, Video, to_dataframe
from shared.utils import privacy
from shared.utils import snapshots as s

T = datetime(2026, 9, 30, 8, 0, tzinfo=timezone.utc)
SALT = b"test-salt-" + b"0" * 54
RAW = {k: f"UC_raw_ppr_{k}_xxxxxxxx" for k in ("P1", "P2", "P3")}
P = {k: privacy.pseudonymize_id(v, SALT) for k, v in RAW.items()}
CH = {k: f"UC_test_{k}" for k in "ABCDE"}
CN = {k: f"channel:{v}" for k, v in CH.items()}


def build_snapshot():
    chans = [Channel(channel_id=c, channel_name=k, collected_at=T) for k, c in CH.items()]
    vids = [Video(video_id=v, channel_id=CH[v[0]], title=v, published_at="2026-09-01T00:00:00Z", collected_at=T)
            for v in ("A1", "B1", "B2", "C1", "D1")]
    inter = [("P1", "A1"), ("P1", "A1"), ("P1", "B1"), ("P2", "B2"), ("P2", "C1"), ("P3", "D1")]
    comms = [Comment(comment_id=f"k{i}", video_id=v, channel_id=CH[v[0]], author_channel_id=P[w],
                     comment_text="Synthetic.", published_at=f"2026-09-{i + 2:02d}T10:00:00Z", collected_at=T)
             for i, (w, v) in enumerate(inter)]
    frames = {"channels": to_dataframe(chans, Channel), "videos": to_dataframe(vids, Video),
              "comments": to_dataframe(comms, Comment)}
    return s.create_research_snapshot(frames, source="synthetic_test").snapshot_id


@pytest.fixture
def graph(isolated_data_dir, monkeypatch):
    times = iter(datetime(2026, 10, 8, 14, 0, tzinfo=timezone.utc) + timedelta(seconds=i) for i in range(100))
    monkeypatch.setattr(s, "_utcnow", lambda: next(times))
    return hg.build_graph(build_snapshot())


@pytest.fixture
def run(graph):
    return ppr.run_diffusion(graph)


def row(run, src, dst):
    r = run.results
    hit = r[(r.source_channel_id == CN[src]) & (r.destination_channel_id == CN[dst])]
    assert len(hit) == 1
    return hit.iloc[0]


# --- transitions / direction -------------------------------------------------------------------

def test_transition_probabilities(graph):
    dg = ppr.build_diffusion_graph(graph)
    rows = np.asarray(dg.transition.sum(axis=1)).ravel()
    assert np.allclose(rows[~dg.dangling], 1.0) and (rows[dg.dangling] == 0).all()
    e = dg.edges
    p1 = e[e.source == f"commenter:{P['P1']}"].set_index("target")["probability"]
    # P1: 2 comments on A1 (w = ln 3), 1 on B1 (w = ln 2)  ->  P = w / sum w
    assert p1["video:A1"] == pytest.approx(np.log(3) / (np.log(3) + np.log(2)))
    assert p1["video:B1"] == pytest.approx(np.log(2) / (np.log(3) + np.log(2)))


def test_bidirectional_with_labelled_reverse_edges(graph):
    dg = ppr.build_diffusion_graph(graph)
    e = dg.edges
    fwd = e[(e.source == f"commenter:{P['P1']}") & (e.target == "video:A1")].iloc[0]
    rev = e[(e.source == "video:A1") & (e.target == f"commenter:{P['P1']}")].iloc[0]
    assert (fwd.kind, fwd.direction) == ("observed", "forward")
    assert (rev.kind, rev.direction) == ("derived_diffusion_edge", "reverse")
    assert not (e["relation"] == "participates_in").any()  # derived shortcut excluded by default
    assert (ppr.build_diffusion_graph(graph, ppr.PPRConfig(include_derived_participation=True))
            .edges["relation"] == "participates_in").any()


def test_relation_balanced_rule(graph):
    dg = ppr.build_diffusion_graph(graph, ppr.PPRConfig(transition_rule="relation_balanced"))
    e = dg.edges
    b1 = e[e.source == "video:B1"].set_index("target")["probability"]
    # video B1 has two groups (comments:reverse -> P1, belongs_to:forward -> B): 1/2 each
    assert b1[f"commenter:{P['P1']}"] == pytest.approx(0.5) and b1[CN["B"]] == pytest.approx(0.5)


def test_relation_weight_multiplier_and_invalid_config(graph):
    dg = ppr.build_diffusion_graph(graph, ppr.PPRConfig(relation_weights=(("belongs_to:forward", 0.0),)))
    assert not ((dg.edges.relation == "belongs_to") & (dg.edges.direction == "forward")).any()
    for bad in (ppr.PPRConfig(transition_rule="flat"), ppr.PPRConfig(directionality="directed"),
                ppr.PPRConfig(relation_weights=(("likes:forward", 1.0),))):
        with pytest.raises(ppr.DiffusionError):
            ppr.build_diffusion_graph(graph, bad)


# --- personalization / convergence / dangling ---------------------------------------------------

def test_personalization_vector(graph):
    dg = ppr.build_diffusion_graph(graph)
    p = ppr.personalization_vector(dg, graph, CN["A"], "source_channel")
    assert p.sum() == 1.0 and p[dg.index[CN["A"]]] == 1.0
    pv = ppr.personalization_vector(dg, graph, CN["B"], "source_channel_videos")
    assert pv[dg.index["video:B1"]] == pv[dg.index["video:B2"]] == 0.5
    with pytest.raises(ppr.DiffusionError):
        ppr.personalization_vector(dg, graph, "video:A1", "source_channel")


def test_convergence_and_mass(run):
    for src, conv in run.metadata["convergence"].items():
        assert conv["converged"] and conv["residual"] < 1e-10 and conv["total_mass"] == pytest.approx(1.0)


def test_non_convergence_recorded(graph):
    r = ppr.run_diffusion(graph, ppr.PPRConfig(max_iterations=2), sources=[CN["A"]])
    conv = r.metadata["convergence"][CN["A"]]
    assert conv["converged"] is False and conv["iterations"] == 2
    assert r.metadata["validation"]["not_converged_sources"] == [CN["A"]]


def test_dangling_source_is_safe(graph):
    r = ppr.run_diffusion(graph, sources=[CN["E"]])  # channel without videos
    assert np.isfinite(r.results["diffusion_score"]).all()
    assert (r.results["diffusion_score"] == 0).all() and not r.results["reachable"].any()
    default = ppr.run_diffusion(graph)
    assert CN["E"] not in default.metadata["sources"] and CN["E"] in default.metadata["skipped_sources"]


# --- qualitative / mathematical properties ------------------------------------------------------

def test_connectivity_order_from_a(run):
    b, c, d = row(run, "A", "B"), row(run, "A", "C"), row(run, "A", "D")
    assert b.diffusion_score > c.diffusion_score > 0       # B is 1 commenter away, C two hops further
    assert d.diffusion_score == 0 and not d.reachable     # disconnected: no fabricated connection
    assert (b["rank"], c["rank"]) == (1, 2)


def test_disconnected_component(run):
    r = run.results
    from_d = r[r.source_channel_id == CN["D"]]
    assert (from_d["diffusion_score"] == 0).all() and not from_d["reachable"].any()


def test_multiple_sources_independent(graph, run):
    assert set(run.results["source_channel_id"]) == {CN[k] for k in "ABCD"}
    alone = ppr.run_diffusion(graph, sources=[CN["B"]]).results
    together = run.results[run.results.source_channel_id == CN["B"]].reset_index(drop=True)
    pd.testing.assert_frame_equal(alone.drop(columns="experiment_id"), together.drop(columns="experiment_id"))


def test_self_channel_handling(graph, run):
    assert not run.results["is_source"].any()
    assert not (run.results.source_channel_id == run.results.destination_channel_id).any()
    inc = ppr.run_diffusion(graph, ppr.PPRConfig(include_source=True), sources=[CN["A"]]).results
    assert inc["is_source"].sum() == 1 and inc.iloc[0]["destination_channel_id"] == CN["A"]  # most mass stays home


def test_normalized_share_is_labelled_and_sums_to_one(run):
    for src, df in run.results.groupby("source_channel_id"):
        if df["diffusion_score"].sum() > 0:
            assert df["normalized_destination_share"].sum() == pytest.approx(1.0)
    raw_total = run.results[run.results.source_channel_id == CN["A"]]["diffusion_score"].sum()
    assert raw_total < 1.0  # raw scores are kept (mass also sits on videos / commenters / source)


# --- determinism / schema / persistence / privacy ---------------------------------------------------

def test_deterministic(graph):
    a, b = ppr.run_diffusion(graph), ppr.run_diffusion(graph)
    pd.testing.assert_frame_equal(a.results, b.results)
    assert a.experiment_id == b.experiment_id
    assert ppr.run_diffusion(graph, ppr.PPRConfig(alpha=0.5)).experiment_id != a.experiment_id


def test_result_schema(run):
    assert list(run.results.columns) == list(ppr.RESULT_COLUMNS)
    r = run.results
    assert (r["snapshot_id"] == run.snapshot_id).all() and (r["experiment_id"] == run.experiment_id).all()
    assert np.isfinite(r["diffusion_score"]).all() and (r["diffusion_score"] >= 0).all()


def test_metadata(run):
    md = run.metadata
    c = md["config"]
    assert (c["alpha"], c["tolerance"], c["max_iterations"]) == (0.85, 1e-10, 1000)
    assert c["directionality"] == "relation_aware_bidirectional" and c["personalization"] == "source_channel"
    assert c["include_source"] is False and md["edge_weighting_version"].startswith("step14")
    assert md["graph_fingerprint"] and md["created_at"].endswith("Z")
    assert md["diffusion_graph"]["derived_diffusion_edges"] == md["diffusion_graph"]["observed_edges"]
    assert "not an Audience Bridge Score" in md["note"]


def test_save_load_and_tamper(run):
    path = ppr.save_run(run)
    loaded = ppr.load_run(path)
    pd.testing.assert_frame_equal(loaded.results, run.results)
    assert ppr.save_run(run) == path
    df = pd.read_parquet(path / "channel_diffusion.parquet")
    df.loc[0, "diffusion_score"] = 0.5
    df.to_parquet(path / "channel_diffusion.parquet", index=False)
    with pytest.raises(ppr.DiffusionError, match="checksum"):
        ppr.load_run(path)


def test_invalid_alpha_and_unknown_source(graph):
    with pytest.raises(ppr.DiffusionError):
        ppr.run_diffusion(graph, ppr.PPRConfig(alpha=1.0))
    with pytest.raises(ppr.DiffusionError, match="unknown source"):
        ppr.run_diffusion(graph, sources=["channel:UC_nope"])


def test_no_raw_commenter_ids(run):
    path = ppr.save_run(run)
    blob = " ".join([run.results.to_csv(), json.dumps(run.metadata, default=str)]
                    + [p.read_bytes().decode("latin-1") for p in path.iterdir()])
    for raw in RAW.values():
        assert raw not in blob
    assert run.results["destination_channel_id"].str.startswith("channel:").all()


def test_no_bridge_score(run):
    assert not any("bridge" in c for c in run.results.columns)
