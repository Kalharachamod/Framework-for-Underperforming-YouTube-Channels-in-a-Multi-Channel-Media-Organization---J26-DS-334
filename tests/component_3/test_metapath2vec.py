"""Tests for metapath2vec (Component 3 primary representation learning).

TEST DATA (synthetic): channels A, B, C (C has no videos); videos A1, A2 (A), B1 (B);
commenters P1 (A1, B1), P2 (A2), P3 (B1). Built through the real STEP 12 -> STEP 13
pipeline. Pseudonyms come from a test salt; raw ids are never printed.
"""

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from subprocess import run
import sys

import numpy as np
import pandas as pd
import pytest

from research.component_3.model import metapath2vec as m2v
from research.component_3.preprocessing import hetero_graph as hg
from shared.schemas import Channel, Comment, Video, to_dataframe
from shared.utils import privacy
from shared.utils import snapshots as s

T = datetime(2026, 9, 30, 8, 0, tzinfo=timezone.utc)
SALT = b"test-salt-" + b"0" * 54
RAW = {k: f"UC_raw_m2v_{k}_xxxxxxxx" for k in ("P1", "P2", "P3")}
P = {k: privacy.pseudonymize_id(v, SALT) for k, v in RAW.items()}
CH = {"A": "UC_test_A", "B": "UC_test_B", "C": "UC_test_C"}
SMALL = m2v.Config(walks_per_node=3, walk_length=10, dimensions=8, window=2, negative=2, epochs=2, seed=7)


def build_snapshot():
    chans = [Channel(channel_id=c, channel_name=k, collected_at=T) for k, c in CH.items()]
    vids = [Video(video_id=v, channel_id=CH[c], title=v, published_at="2026-09-01T00:00:00Z", collected_at=T)
            for v, c in (("A1", "A"), ("A2", "A"), ("B1", "B"))]

    def cm(cid, vid, ch, who, day):
        at = f"2026-09-{day:02d}T10:00:00Z"
        return Comment(comment_id=cid, video_id=vid, channel_id=CH[ch], author_channel_id=P[who],
                       comment_text="Synthetic.", published_at=at, collected_at=T)

    comms = [cm("k1", "A1", "A", "P1", 5), cm("k2", "A1", "A", "P1", 6), cm("k3", "B1", "B", "P1", 7),
             cm("k4", "A2", "A", "P2", 8), cm("k5", "B1", "B", "P3", 9)]
    frames = {"channels": to_dataframe(chans, Channel), "videos": to_dataframe(vids, Video),
              "comments": to_dataframe(comms, Comment)}
    return s.create_research_snapshot(frames, source="synthetic_test").snapshot_id


@pytest.fixture
def ticking(monkeypatch):
    times = iter(datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc) + timedelta(seconds=i) for i in range(100))
    monkeypatch.setattr(s, "_utcnow", lambda: next(times))


@pytest.fixture
def graph(isolated_data_dir, ticking):
    return hg.build_graph(build_snapshot())


@pytest.fixture
def result(graph):
    return m2v.train(graph, SMALL)


def types(graph):
    return dict(zip(graph.nodes["node_id"], graph.nodes["node_type"]))


# --- meta-path validation ------------------------------------------------------------------

def test_default_metapaths_valid(graph):
    for mp in m2v.DEFAULT_METAPATHS:
        assert m2v.validate_metapath(mp, graph) == [], mp.name


@pytest.mark.parametrize("mp, message", [
    (m2v.MetaPath("bad_type", ("commenter", "clip", "commenter"), ("comments", "comments"), ""), "invalid node type"),
    (m2v.MetaPath("bad_rel", ("commenter", "video", "commenter"), ("likes", "likes"), ""), "invalid relation"),
    (m2v.MetaPath("bad_step", ("commenter", "channel", "commenter"), ("comments", "comments"), ""), "cannot connect"),
    (m2v.MetaPath("derived", ("commenter", "channel", "commenter"), ("participates_in", "participates_in"), ""),
     "derived"),
    (m2v.MetaPath("one_way", ("commenter", "video", "channel"), ("comments", "belongs_to"), ""), "same node type"),
    (m2v.MetaPath("lengths", ("commenter", "video"), ("comments", "comments"), ""), "n-1 relations"),
])
def test_invalid_metapaths(graph, mp, message):
    assert any(message in p for p in m2v.validate_metapath(mp, graph))


def test_topic_metapath_reported_unavailable(graph):
    problems = m2v.validate_metapath(m2v.TOPIC_METAPATHS[0], graph)
    assert any("topic modelling has not run yet" in p for p in problems)
    cfg = replace(SMALL, metapaths=m2v.DEFAULT_METAPATHS + m2v.TOPIC_METAPATHS)
    walks, stats = m2v.generate_walks(graph, cfg)
    assert "VTV" in stats["skipped_metapaths"] and walks  # skipped, not fabricated


def test_no_usable_metapath_fails(graph):
    with pytest.raises(m2v.MetaPathError):
        m2v.generate_walks(graph, replace(SMALL, metapaths=m2v.TOPIC_METAPATHS))


# --- walks ----------------------------------------------------------------------------------

def test_walks_follow_metapaths_and_edges(graph):
    walks, stats = m2v.generate_walks(graph, SMALL)
    t = types(graph)
    edges = set(zip(graph.edges["source"], graph.edges["target"])) | set(zip(graph.edges["target"], graph.edges["source"]))
    walkable = graph.edges[graph.edges["relation"].isin(m2v.WALKABLE_RELATIONS)]
    walk_edges = set(zip(walkable["source"], walkable["target"])) | set(zip(walkable["target"], walkable["source"]))
    offset = 0
    for mp in m2v.DEFAULT_METAPATHS:
        n = stats["per_metapath"][mp.name]["walks"]
        for w in walks[offset:offset + n]:
            assert m2v.walk_respects_metapath(w, mp, t), (mp.name, w)
            assert all((a, b) in walk_edges for a, b in zip(w, w[1:]))  # only real, non-derived edges
            assert len(w) <= SMALL.walk_length
        offset += n
    assert offset == len(walks) and edges


def test_walk_statistics_and_truncation(graph):
    _, stats = m2v.generate_walks(graph, SMALL)
    assert stats["per_metapath"]["CVC"] == {"start_nodes": 3, "walks": 9, "truncated": 0}
    # channel C has no videos: ChVCVCh walks from it stop immediately and are dropped
    assert stats["per_metapath"]["ChVCVCh"]["walks"] == 2 * SMALL.walks_per_node
    assert stats["per_metapath"]["ChVCVCh"]["truncated"] == SMALL.walks_per_node


def test_walks_reproducible_and_seed_sensitive(graph):
    a, _ = m2v.generate_walks(graph, SMALL)
    b, _ = m2v.generate_walks(graph, SMALL)
    c, _ = m2v.generate_walks(graph, replace(SMALL, seed=8))
    assert a == b and a != c


def test_weighted_transitions_respect_weights(graph):
    cfg = replace(SMALL, transition_weights="log1p_comments", walks_per_node=200,
                  metapaths=(m2v.DEFAULT_METAPATHS[0],))
    walks, _ = m2v.generate_walks(graph, cfg)
    # From P1, video A1 (2 comments, weight ln3) should be chosen more often than B1 (1 comment, ln2).
    p1 = f"commenter:{P['P1']}"
    nxt = [w[1] for w in walks if w[0] == p1]
    assert nxt.count("video:A1") > nxt.count("video:B1")
    with pytest.raises(ValueError):
        m2v.generate_walks(graph, replace(SMALL, transition_weights="pagerank"))


# --- training / embeddings ---------------------------------------------------------------------

def test_embedding_shape_types_and_finiteness(graph, result):
    assert result.vectors.shape == (len(result.nodes), SMALL.dimensions)
    assert np.isfinite(result.vectors).all()
    t = types(graph)
    assert all(t[n] == nt for n, nt in zip(result.nodes["node_id"], result.nodes["node_type"]))
    assert result.metadata["validation"]["passed"]
    commenters, cv = result.of_type("commenter")
    assert len(commenters) == 3 and cv.shape == (3, SMALL.dimensions)


def test_coverage(graph, result):
    cov = result.metadata["coverage"]
    assert cov["per_type"]["commenter"] == {"graph_nodes": 3, "embedded": 3, "missing": 0}
    assert cov["per_type"]["video"]["missing"] == 0
    assert cov["per_type"]["channel"] == {"graph_nodes": 3, "embedded": 2, "missing": 1}  # C: no videos
    assert cov["nodes_without_embeddings"] == 1 and "no usable meta-path walk" in cov["why_missing"]
    with pytest.raises(m2v.EmbeddingValidationError, match="coverage"):
        m2v.validate_embeddings(result, graph, SMALL, min_coverage=0.95)


def test_training_reproducible(graph):
    a, b = m2v.train(graph, SMALL), m2v.train(graph, SMALL)
    assert a.experiment_id == b.experiment_id
    np.testing.assert_allclose(a.vectors, b.vectors, atol=1e-6)
    c = m2v.train(graph, replace(SMALL, seed=99))
    assert c.experiment_id != a.experiment_id and not np.allclose(a.vectors, c.vectors)


def test_training_reproducible_across_processes(graph, isolated_data_dir):
    code = (
        "import json,sys; from research.component_3.model import metapath2vec as m;"
        "from research.component_3.preprocessing import hetero_graph as hg;"
        f"g=hg.load_graph(hg.graph_dir('{graph.snapshot_id}'));"
        "c=m.Config(walks_per_node=3,walk_length=10,dimensions=8,window=2,negative=2,epochs=2,seed=7);"
        "r=m.train(g,c); print(json.dumps(r.vectors.round(5).tolist()))")
    hg.save_graph(graph)
    import os
    env = {**os.environ, "DATA_DIR": str(isolated_data_dir)}
    outs = [run([sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True).stdout
            for _ in range(2)]
    assert outs[0] == outs[1]
    np.testing.assert_allclose(np.array(json.loads(outs[0])), m2v.train(graph, SMALL).vectors, atol=1e-4)


def test_invalid_embeddings_detected(graph, result):
    bad = m2v.EmbeddingResult(result.snapshot_id, result.experiment_id, result.nodes, result.vectors.copy())
    bad.vectors[0, 0] = np.nan
    with pytest.raises(m2v.EmbeddingValidationError, match="NaN"):
        m2v.validate_embeddings(bad, graph, SMALL)
    wrong = m2v.EmbeddingResult(result.snapshot_id, result.experiment_id,
                                result.nodes.assign(node_type="video").astype("string"), result.vectors)
    with pytest.raises(m2v.EmbeddingValidationError, match="node type"):
        m2v.validate_embeddings(wrong, graph, SMALL)
    with pytest.raises(m2v.EmbeddingValidationError, match="shape"):
        m2v.validate_embeddings(result, graph, replace(SMALL, dimensions=16))


# --- metadata / persistence ----------------------------------------------------------------

def test_experiment_metadata(result):
    md = result.metadata
    assert md["method"] == "metapath2vec" and md["experiment_id"].startswith("m2v-")
    assert md["snapshot_id"] == result.snapshot_id and md["graph_fingerprint"]
    cfg = md["config"]
    assert (cfg["dimensions"], cfg["walk_length"], cfg["walks_per_node"], cfg["window"], cfg["negative"],
            cfg["epochs"], cfg["seed"]) == (8, 10, 3, 2, 2, 2, 7)
    assert [mp["name"] for mp in cfg["metapaths"]] == ["CVC", "CVChVC", "ChVCVCh", "VChV"]
    assert {"python", "numpy", "gensim"} <= set(md["versions"]) and md["created_at"].endswith("Z")
    assert "does not show audience migration" in md["note"]


def test_save_and_reload(result):
    path = m2v.save_embeddings(result)
    assert {p.name for p in path.iterdir()} == {"embeddings.parquet", "embeddings.npy", "experiment.json"}
    loaded = m2v.load_embeddings(path)
    assert loaded.nodes["node_id"].tolist() == result.nodes["node_id"].tolist()
    np.testing.assert_allclose(loaded.vectors, result.vectors)
    table = pd.read_parquet(path / "embeddings.parquet")
    assert list(table.columns) == ["node_id", "node_type", "snapshot_id", "experiment_id", "embedding"]
    assert set(table["experiment_id"]) == {result.experiment_id} and len(table["embedding"][0]) == 8
    meta = json.loads((path / "experiment.json").read_text(encoding="utf-8"))
    assert meta["config"]["seed"] == 7
    assert m2v.save_embeddings(result) == path  # identical: accepted


def test_tampering_detected(result):
    path = m2v.save_embeddings(result)
    v = np.load(path / "embeddings.npy")
    v[0, 0] += 1
    np.save(path / "embeddings.npy", v)
    with pytest.raises(m2v.EmbeddingValidationError, match="checksum"):
        m2v.load_embeddings(path)


# --- sanity checks / privacy ---------------------------------------------------------------------

def test_nearest_neighbours_and_exploratory_label(result):
    nn = m2v.nearest_neighbours(result, f"commenter:{P['P1']}", k=5)
    assert len(nn) == 2 and set(nn["node_type"]) == {"commenter"}
    assert (nn["cosine_similarity"].between(-1, 1)).all()
    ch = m2v.channel_similarity_exploratory(result, f"channel:{CH['A']}", k=3)
    assert ch["node_id"].tolist() == [f"channel:{CH['B']}"]
    assert set(ch["label"]) == {"Embedding similarity — exploratory"}


def test_no_raw_commenter_ids(result):
    path = m2v.save_embeddings(result)
    blob = " ".join([result.nodes.to_csv(), json.dumps(result.metadata, default=str)]
                    + [p.read_bytes().decode("latin-1") for p in path.iterdir()])
    for raw in RAW.values():
        assert raw not in blob


def test_no_later_stage_methods(result):
    assert not any(k in json.dumps(result.metadata).lower() for k in ("pagerank_score", "bridge_score", "hgt"))
