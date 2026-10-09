"""Tests for the Component 3 baselines (Louvain, node2vec).

TEST DATA (synthetic): two groups of channels joined by shared commenters,
  group 1: A, B, C  (commenters G1..G4 comment across A/B/C)
  group 2: D, E     (commenters H1..H3 comment across D/E)
  F: own commenter only (isolated in the channel projection);  X: no videos
Built through the real STEP 12 -> 13 -> 14 pipeline. Pseudonyms from a test salt.
"""

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from research.component_3.model import baselines as bl
from research.component_3.preprocessing import hetero_graph as hg
from shared.schemas import Channel, Comment, Video, to_dataframe
from shared.utils import privacy
from shared.utils import snapshots as s

T = datetime(2026, 9, 30, 8, 0, tzinfo=timezone.utc)
SALT = b"test-salt-" + b"0" * 54
WHO = ["G1", "G2", "G3", "G4", "H1", "H2", "H3", "F1"]
RAW = {k: f"UC_raw_base_{k}_xxxxxxx" for k in WHO}
P = {k: privacy.pseudonymize_id(v, SALT) for k, v in RAW.items()}
CH = {k: f"UC_test_{k}" for k in "ABCDEFX"}
CN = {k: f"channel:{v}" for k, v in CH.items()}
VIDEOS = {"A1": "A", "A2": "A", "B1": "B", "C1": "C", "D1": "D", "E1": "E", "F1v": "F"}
INTERACTIONS = [("G1", "A1"), ("G1", "B1"), ("G2", "B1"), ("G2", "C1"), ("G3", "A2"), ("G3", "C1"),
                ("G4", "A1"), ("G4", "B1"), ("G4", "C1"), ("H1", "D1"), ("H1", "E1"), ("H2", "D1"),
                ("H2", "E1"), ("H3", "E1"), ("H3", "D1"), ("F1", "F1v")]
SMALL_N2V = bl.Node2VecConfig(dimensions=8, walk_length=10, walks_per_node=3, window=2, negative=2, epochs=2, seed=5)


def build_snapshot(interactions=INTERACTIONS, channels="ABCDEFX", videos=None):
    videos = videos if videos is not None else VIDEOS
    chans = [Channel(channel_id=CH[k], channel_name=k, collected_at=T) for k in channels]
    vids = [Video(video_id=v, channel_id=CH[c], title=v, published_at="2026-09-01T00:00:00Z", collected_at=T)
            for v, c in videos.items() if c in channels]
    comms = [Comment(comment_id=f"k{i}", video_id=v, channel_id=CH[videos[v]], author_channel_id=P[w],
                     comment_text="Synthetic.", published_at=f"2026-09-{(i % 25) + 2:02d}T10:00:00Z", collected_at=T)
             for i, (w, v) in enumerate(interactions)]
    frames = {"channels": to_dataframe(chans, Channel), "videos": to_dataframe(vids, Video),
              "comments": to_dataframe(comms, Comment)}
    return s.create_research_snapshot(frames, source="synthetic_test",
                                      extracted_at=datetime(2026, 10, 1, tzinfo=timezone.utc)).snapshot_id


@pytest.fixture
def ticking(monkeypatch):
    times = iter(datetime(2026, 10, 9, 10, 0, tzinfo=timezone.utc) + timedelta(seconds=i) for i in range(300))
    monkeypatch.setattr(s, "_utcnow", lambda: next(times))


@pytest.fixture
def inp(isolated_data_dir, ticking):
    return bl.load_input(build_snapshot())


# --- projection --------------------------------------------------------------------------------

def test_channel_projection(inp):
    e = bl.channel_projection(inp)
    pairs = set(zip(e.channel_a, e.channel_b))
    assert pairs == {(CN["A"], CN["B"]), (CN["A"], CN["C"]), (CN["B"], CN["C"]), (CN["D"], CN["E"])}
    de = e[(e.channel_a == CN["D"]) & (e.channel_b == CN["E"])].iloc[0]
    assert de.shared_commenters == 3 and de.weight == pytest.approx(1.0)  # identical commenter sets -> Jaccard 1
    w = bl.channel_projection(inp, "log1p_shared")
    assert w["weight"].tolist() == pytest.approx(np.log1p(w["shared_commenters"]).tolist())
    with pytest.raises(bl.BaselineError):
        bl.channel_projection(inp, "magic")


def test_projection_rejects_duplicate_pairs(inp):
    dup = replace(inp, pair_features=pd.concat([inp.pair_features, inp.pair_features.iloc[[0]]]))
    with pytest.raises(bl.BaselineError, match="duplicate"):
        bl.channel_projection(dup)


# --- Louvain ------------------------------------------------------------------------------------

def test_louvain_separates_groups(inp):
    r = bl.run_louvain(inp)
    comm = dict(zip(r.communities.channel_id, r.communities.community_id))
    assert comm[CN["A"]] == comm[CN["B"]] == comm[CN["C"]]
    assert comm[CN["D"]] == comm[CN["E"]] != comm[CN["A"]]
    assert len({comm[CN["F"]], comm[CN["X"]], comm[CN["A"]], comm[CN["D"]]}) == 4  # isolated -> singletons
    c = r.communities.set_index("channel_id")
    assert c.loc[CN["A"], "community_size"] == 3 and c.loc[CN["F"], "is_isolated"] and c.loc[CN["X"], "is_isolated"]
    assert c.loc[CN["A"], "community_id"] == "c00"  # largest community first


def test_louvain_deterministic_and_metadata(inp):
    a, b = bl.run_louvain(inp), bl.run_louvain(inp)
    pd.testing.assert_frame_equal(a.communities, b.communities)
    assert a.experiment_id == b.experiment_id and a.experiment_id.startswith("louvain-")
    m = a.metadata
    assert m["method"] == "louvain" and m["seed"] == 42 and m["snapshot_id"] == inp.snapshot_id
    assert m["parameters"]["resolution"] == 1.0 and m["channel_set"] == inp.channels
    assert "not the proposed method" in m["role"] and "does not show audience migration" in m["note"]
    assert bl.run_louvain(inp, bl.LouvainConfig(resolution=2.0)).experiment_id != a.experiment_id


def test_louvain_relationships(inp):
    rel = bl.run_louvain(inp).relationships
    assert len(rel) == 7 * 6 and not (rel.source_channel_id == rel.destination_channel_id).any()
    ab = rel[(rel.source_channel_id == CN["A"]) & (rel.destination_channel_id == CN["B"])].iloc[0]
    ad = rel[(rel.source_channel_id == CN["A"]) & (rel.destination_channel_id == CN["D"])].iloc[0]
    assert ab.same_community and ab.community_relationship == 1.0 and ab.shared_commenters > 0
    assert not ad.same_community and ad.community_relationship == 0.0 and ad.shared_commenters == 0
    assert (rel.snapshot_id == inp.snapshot_id).all()


def test_louvain_weighted_graph_handling(inp):
    r = bl.run_louvain(inp, bl.LouvainConfig(projection_weight="shared_commenters"))
    assert r.metadata["edge_weight_definition"].startswith("STEP 14 shared_commenter_count")
    assert r.metadata["modularity"] is not None


def test_louvain_invalid_config(inp):
    with pytest.raises(bl.BaselineError):
        bl.run_louvain(inp, bl.LouvainConfig(resolution=0))


# --- node2vec ------------------------------------------------------------------------------------

def test_node2vec_embeddings_and_similarity(inp):
    r = bl.run_node2vec(inp, SMALL_N2V)
    v = r.embeddings.vectors
    assert v.shape[1] == 8 and np.isfinite(v).all()
    chans = set(r.embeddings.nodes.loc[r.embeddings.nodes.node_type == "channel", "node_id"])
    assert chans == {CN[k] for k in "ABCDEF"}  # X has no edges: never walked, no embedding
    sim = r.similarity
    assert list(sim.columns) == ["source_channel_id", "destination_channel_id", "raw_node2vec_similarity",
                                 "normalized_node2vec_similarity", "rank", "snapshot_id", "experiment_id"]
    assert not (sim.source_channel_id == sim.destination_channel_id).any()
    x = sim[sim.destination_channel_id == CN["X"]]
    assert x["raw_node2vec_similarity"].isna().all() and x["rank"].isna().all()
    ok = sim.dropna(subset=["raw_node2vec_similarity"])
    assert ok["normalized_node2vec_similarity"].tolist() == pytest.approx(((ok["raw_node2vec_similarity"] + 1) / 2).tolist())


def test_node2vec_cosine_matches_vectors(inp):
    r = bl.run_node2vec(inp, SMALL_N2V)
    va, vb = r.embeddings.vector(CN["A"]), r.embeddings.vector(CN["B"])
    expected = float(va @ vb / (np.linalg.norm(va) * np.linalg.norm(vb)))
    got = r.similarity[(r.similarity.source_channel_id == CN["A"]) & (r.similarity.destination_channel_id == CN["B"])]
    assert got["raw_node2vec_similarity"].iloc[0] == pytest.approx(expected, abs=1e-6)
    ba = r.similarity[(r.similarity.source_channel_id == CN["B"]) & (r.similarity.destination_channel_id == CN["A"])]
    assert ba["raw_node2vec_similarity"].iloc[0] == pytest.approx(expected, abs=1e-6)  # symmetric


def test_node2vec_ranking_and_tie_breaking():
    emb = bl.m2v.EmbeddingResult("snap", "e", pd.DataFrame(
        {"node_id": ["channel:a", "channel:b", "channel:c", "channel:d"], "node_type": ["channel"] * 4}),
        np.array([[1, 0], [1, 0], [1, 0], [0, 1]], dtype=np.float32))
    sim = bl.channel_similarity(emb, ["channel:a", "channel:b", "channel:c", "channel:d"])
    a = sim[sim.source_channel_id == "channel:a"]
    assert a["destination_channel_id"].tolist() == ["channel:b", "channel:c", "channel:d"]  # b, c tie -> by id
    assert a["rank"].tolist() == [1, 2, 3] and a["raw_node2vec_similarity"].tolist() == [1.0, 1.0, 0.0]


def test_node2vec_deterministic(inp):
    a, b = bl.run_node2vec(inp, SMALL_N2V), bl.run_node2vec(inp, SMALL_N2V)
    np.testing.assert_allclose(a.embeddings.vectors, b.embeddings.vectors, atol=1e-6)
    pd.testing.assert_frame_equal(a.similarity, b.similarity)
    assert a.experiment_id == b.experiment_id and a.experiment_id.startswith("node2vec-")


def test_node2vec_walk_bias_parameters(inp):
    adj = bl.homogeneous_adjacency(inp.graph, weighted=True)
    walks_back = bl.node2vec_walks(adj, replace(SMALL_N2V, p=0.01, q=100))   # strongly prefers returning
    walks_out = bl.node2vec_walks(adj, replace(SMALL_N2V, p=100, q=0.01))    # strongly prefers moving away
    returns = lambda ws: np.mean([w[i] == w[i - 2] for w in ws for i in range(2, len(w))])  # noqa: E731
    assert returns(walks_back) > returns(walks_out)


def test_homogeneous_view_merges_duplicates_and_ignores_derived(inp):
    adj = bl.homogeneous_adjacency(inp.graph, weighted=False)
    assert all(not n.startswith("topic:") for n in adj)
    a = dict(adj[CN["A"]])
    assert set(a) == {"video:A1", "video:A2"}  # channel connects only via belongs_to (no participates_in)


def test_node2vec_metadata(inp):
    m = bl.run_node2vec(inp, SMALL_N2V).metadata
    assert m["method"] == "node2vec" and m["seed"] == 5 and m["parameters"]["p"] == 1.0
    assert "homogeneous" in m["graph_projection"] and m["snapshot_id"] == inp.snapshot_id
    assert "structural graph proximity" in m["note"]


@pytest.mark.parametrize("bad", [dict(dimensions=0), dict(walk_length=1), dict(p=0), dict(q=-1), dict(epochs=0)])
def test_node2vec_invalid_config(inp, bad):
    with pytest.raises(bl.BaselineError):
        bl.run_node2vec(inp, replace(SMALL_N2V, **bad))


# --- persistence / privacy -------------------------------------------------------------------------

def test_save_and_reload(inp):
    lv = bl.run_louvain(inp)
    lp = bl.save_louvain(lv)
    assert {p.name for p in lp.iterdir()} == {"louvain_communities.parquet", "louvain_channel_relationships.parquet",
                                             "baseline_run.json"}
    assert bl.save_louvain(lv) == lp
    nv = bl.run_node2vec(inp, SMALL_N2V)
    np_ = bl.save_node2vec(nv)
    loaded = bl.load_node2vec(np_)
    np.testing.assert_allclose(loaded.embeddings.vectors, nv.embeddings.vectors)
    assert set(pd.read_parquet(np_ / "embeddings.parquet")["model_type"]) == {"node2vec"}
    assert (loaded.similarity["experiment_id"] == nv.experiment_id).all()


def test_no_raw_commenter_ids(inp):
    paths = [bl.save_louvain(bl.run_louvain(inp)), bl.save_node2vec(bl.run_node2vec(inp, SMALL_N2V))]
    blob = " ".join(p2.read_bytes().decode("latin-1") for d in paths for p2 in d.iterdir())
    for raw in RAW.values():
        assert raw not in blob


# --- edge cases ------------------------------------------------------------------------------------

def test_empty_graph(inp):
    empty = replace(inp, channels=[], pair_features=inp.pair_features.iloc[0:0])
    with pytest.raises(bl.BaselineError, match="no channels"):
        bl.run_louvain(empty)
    with pytest.raises(bl.BaselineError, match="no channels"):
        bl.run_node2vec(empty, SMALL_N2V)


def test_one_channel_graph(isolated_data_dir, ticking):
    sid = build_snapshot(interactions=[("G1", "A1"), ("G2", "A2")], channels="A",
                         videos={"A1": "A", "A2": "A"})
    one = bl.load_input(sid)
    r = bl.run_louvain(one)
    assert len(r.communities) == 1 and r.relationships.empty and r.metadata["modularity"] is None
    n = bl.run_node2vec(one, SMALL_N2V)
    assert n.similarity.empty


def test_zero_shared_commenters_disconnected(isolated_data_dir, ticking):
    sid = build_snapshot(interactions=[("G1", "A1"), ("H1", "D1"), ("F1", "F1v")], channels="ADF",
                         videos={"A1": "A", "D1": "D", "F1v": "F"})
    sparse_inp = bl.load_input(sid)
    assert bl.channel_projection(sparse_inp).empty
    r = bl.run_louvain(sparse_inp)
    assert r.communities["community_size"].eq(1).all() and r.communities["is_isolated"].all()
    assert not r.relationships["same_community"].any()
    n = bl.run_node2vec(sparse_inp, SMALL_N2V)
    assert np.isfinite(n.similarity["raw_node2vec_similarity"].dropna()).all()
