"""Tests for HGT (Component 3 alternative graph learning).

TEST DATA (synthetic): channels A, B, C (C has no videos); videos A1..A3 (A), B1..B3 (B);
commenters P1..P6 with comments spread over time, built through the real
STEP 12 -> 13 -> 14 pipeline. Pseudonyms from a test salt; raw ids never printed.
"""

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("torch_geometric")

from research.component_3.model import hgt  # noqa: E402
from research.component_3.model import metapath2vec as m2v  # noqa: E402
from research.component_3.preprocessing import hetero_graph as hg  # noqa: E402
from shared.schemas import Channel, Comment, Video, to_dataframe  # noqa: E402
from shared.utils import privacy  # noqa: E402
from shared.utils import snapshots as s  # noqa: E402

T = datetime(2026, 9, 30, 8, 0, tzinfo=timezone.utc)
SALT = b"test-salt-" + b"0" * 54
WHO = [f"P{i}" for i in range(1, 7)]
RAW = {k: f"UC_raw_hgt_{k}_xxxxxxxx" for k in WHO}
P = {k: privacy.pseudonymize_id(v, SALT) for k, v in RAW.items()}
CH = {"A": "UC_test_A", "B": "UC_test_B", "C": "UC_test_C"}
TINY = hgt.HGTConfig(hidden=8, layers=1, heads=2, dropout=0.0, epochs=5, negatives_per_positive=2,
                     validation_fraction=0.25, min_validation_edges=2, seed=3)

# (commenter, video, day): P1..P3 on A, P4..P6 on B, P3 and P4 on both; later days repeat earlier pairs
INTERACTIONS = [("P1", "A1", 1), ("P1", "A2", 2), ("P2", "A1", 3), ("P2", "A3", 4), ("P3", "A2", 5),
                ("P3", "B1", 6), ("P4", "B1", 7), ("P4", "A3", 8), ("P5", "B2", 9), ("P5", "B3", 10),
                ("P6", "B2", 11), ("P6", "B1", 12), ("P1", "A3", 20), ("P5", "B1", 21), ("P2", "A2", 22),
                ("P6", "B3", 23)]


def build_snapshot():
    chans = [Channel(channel_id=c, channel_name=k, subscriber_count=100 * (i + 1), view_count=1000,
                     video_count=3, published_at="2018-01-01T00:00:00Z", collected_at=T)
             for i, (k, c) in enumerate(CH.items())]
    vids = [Video(video_id=v, channel_id=CH[v[0]], title=v, published_at="2026-08-01T00:00:00Z",
                  view_count=500, like_count=20, comment_count=5, collected_at=T)
            for v in ("A1", "A2", "A3", "B1", "B2", "B3")]
    comms = [Comment(comment_id=f"k{i}", video_id=v, channel_id=CH[v[0]], author_channel_id=P[w],
                     comment_text="Synthetic.", published_at=f"2026-09-{d:02d}T10:00:00Z", collected_at=T)
             for i, (w, v, d) in enumerate(INTERACTIONS)]
    frames = {"channels": to_dataframe(chans, Channel), "videos": to_dataframe(vids, Video),
              "comments": to_dataframe(comms, Comment)}
    return s.create_research_snapshot(frames, source="synthetic_test",
                                      extracted_at=datetime(2026, 10, 1, tzinfo=timezone.utc)).snapshot_id


@pytest.fixture
def ticking(monkeypatch):
    times = iter(datetime(2026, 10, 8, 13, 0, tzinfo=timezone.utc) + timedelta(seconds=i) for i in range(200))
    monkeypatch.setattr(s, "_utcnow", lambda: next(times))


@pytest.fixture
def graph(isolated_data_dir, ticking):
    return hg.build_graph(build_snapshot())


@pytest.fixture
def trained(graph):
    return hgt.train(graph, TINY)


# --- conversion --------------------------------------------------------------------------

def test_graph_conversion_types_and_relations(graph):
    data, index, stats = hgt.to_hetero_data(graph, graph.edges_of("comments"), None)
    assert set(data.node_types) == {"commenter", "video", "channel"}  # no fabricated topic type
    assert set(data.edge_types) == {("commenter", "comments", "video"), ("video", "rev_comments", "commenter"),
                                    ("video", "belongs_to", "channel"), ("channel", "rev_belongs_to", "video")}
    assert len(index["commenter"]) == 6 and len(index["video"]) == 6 and len(index["channel"]) == 3
    assert index["video"] == sorted(index["video"])
    ei = data["commenter", "comments", "video"].edge_index
    assert ei.shape == (2, len(graph.edges_of("comments")))
    first = graph.edges_of("comments").iloc[0]
    assert (index["commenter"][ei[0, 0]], index["video"][ei[1, 0]]) == (first.source, first.target)
    assert not any("participates_in" in r for _, r, _ in data.edge_types)  # derived edges not used


def test_type_specific_feature_dimensions(graph):
    data, _, _ = hgt.to_hetero_data(graph, graph.edges_of("comments"), None)
    # public features (value + missing flag each) + structural degree features
    assert data["channel"].x.shape == (3, 4 * 2 + 1)
    assert data["video"].x.shape == (6, 4 * 2 + 1)
    assert data["commenter"].x.shape == (6, 3)
    assert all(torch.isfinite(data[t].x).all() for t in data.node_types)


def test_missing_public_features_are_flagged(graph):
    raw = hgt._raw_features(graph, {"channel": sorted(graph.nodes_of("channel")["node_id"])},
                            graph.edges_of("comments"), None)
    assert (raw["channel"][:, 1::2][:, :4] == 1).all()  # no public table -> every value flagged missing


# --- split / negatives ---------------------------------------------------------------------

def test_temporal_split_when_enough_warm_edges(graph):
    sp = hgt.make_split(graph, TINY, datetime(2026, 10, 1, tzinfo=timezone.utc))
    assert sp.kind == "temporal"
    assert sp.train["first_at"].max() < sp.valid["first_at"].min()  # no future edge in training
    assert set(sp.valid["source"]) <= set(sp.train["source"]) and set(sp.valid["target"]) <= set(sp.train["target"])


def test_random_fallback_is_labelled(graph):
    sp = hgt.make_split(graph, replace(TINY, min_validation_edges=50), datetime(2026, 10, 1, tzinfo=timezone.utc))
    assert sp.kind == "random_edge_split_fallback" and "not a temporal evaluation" in sp.reason
    assert set(map(tuple, sp.train[["source", "target"]].values)).isdisjoint(
        set(map(tuple, sp.valid[["source", "target"]].values)))


def test_negative_sampling_valid_reproducible(graph):
    known = {(0, 0), (0, 1), (1, 2)}
    a = hgt.sample_negatives(np.array([0, 1]), 6, known, 3, np.random.default_rng(1))
    b = hgt.sample_negatives(np.array([0, 1]), 6, known, 3, np.random.default_rng(1))
    assert np.array_equal(a[0], b[0]) and np.array_equal(a[1], b[1])
    assert all((x, y) not in known for x, y in zip(*a))       # never a known positive
    assert set(a[0]) <= {0, 1} and (a[1] < 6).all()           # commenter -> video indices only


# --- model / training --------------------------------------------------------------------

def test_forward_pass_shapes(graph):
    data, _, _ = hgt.to_hetero_data(graph, graph.edges_of("comments"), None)
    model = hgt.build_model(data.metadata(), {t: data[t].x.shape[1] for t in data.node_types}, TINY)
    out = model(data.x_dict, data.edge_index_dict)
    assert {t: tuple(v.shape) for t, v in out.items()} == {"commenter": (6, 8), "video": (6, 8), "channel": (3, 8)}


def test_training_and_embeddings(graph, trained):
    result, model = trained
    assert result.vectors.shape == (15, TINY.hidden) and np.isfinite(result.vectors).all()
    types = dict(zip(graph.nodes["node_id"], graph.nodes["node_type"]))
    assert all(types[n] == t for n, t in zip(result.nodes["node_id"], result.nodes["node_type"]))
    assert result.metadata["coverage"]["nodes_without_embeddings"] == 0  # HGT embeds isolated channel C too
    hist = result.metadata["training"]["history"]
    assert len(hist) == TINY.epochs and all(np.isfinite(h["train_loss"]) for h in hist)
    assert 0 <= hist[-1]["valid_roc_auc"] <= 1 and 0 <= hist[-1]["valid_average_precision"] <= 1


def test_reproducible(graph):
    a, _ = hgt.train(graph, TINY)
    b, _ = hgt.train(graph, TINY)
    assert a.experiment_id == b.experiment_id
    np.testing.assert_allclose(a.vectors, b.vectors, atol=1e-5)
    assert a.metadata["training"]["history"] == b.metadata["training"]["history"]


def test_metadata(trained):
    md = trained[0].metadata
    assert md["method"] == "HGT" and md["experiment_id"].startswith("hgt-") and "primary" in md["role"]
    c = md["config"]
    assert (c["hidden"], c["layers"], c["heads"], c["dropout"], c["epochs"], c["seed"]) == (8, 1, 2, 0.0, 5, 3)
    assert md["split"]["kind"] == "temporal" and md["split"]["train_edges"] + md["split"]["validation_edges"] <= 16
    assert md["negative_sampling"]["corrupted_side"] == "video" and md["negative_sampling"]["excludes_known_positives"]
    assert {"torch", "torch_geometric"} <= set(md["versions"]) and md["created_at"].endswith("Z")
    assert "does not show audience migration" in md["note"]


def test_save_reload_with_checkpoint(trained):
    result, model = trained
    path = hgt.save(result, model)
    assert {p.name for p in path.iterdir()} == {"embeddings.parquet", "embeddings.npy", "experiment.json", "model.pt"}
    loaded = m2v.load_embeddings(path)
    np.testing.assert_allclose(loaded.vectors, result.vectors)
    assert set(pd.read_parquet(path / "embeddings.parquet")["model_type"]) == {"HGT"}
    ckpt = torch.load(path / "model.pt", weights_only=False)
    assert ckpt["experiment_id"] == result.experiment_id and ckpt["config"]["hidden"] == 8
    assert json.loads((path / "experiment.json").read_text(encoding="utf-8"))["split"]["kind"] == "temporal"


def test_exploratory_similarity_label(trained):
    result, _ = trained
    df = hgt.hgt_similarity_exploratory(result, f"channel:{CH['A']}", 2)
    assert set(df["label"]) == {"HGT embedding similarity — exploratory"} and len(df) == 2


def test_no_raw_commenter_ids(trained):
    result, model = trained
    path = hgt.save(result, model)
    blob = " ".join([result.nodes.to_csv(), json.dumps(result.metadata, default=str)]
                    + [p.read_bytes().decode("latin-1") for p in path.iterdir()])
    for raw in RAW.values():
        assert raw not in blob


def test_comparable_with_metapath2vec(graph, trained):
    hgt_result, _ = trained
    m2v_result = m2v.train(graph, m2v.Config(walks_per_node=2, walk_length=8, dimensions=8, window=2,
                                            negative=2, epochs=1, seed=3))
    assert hgt_result.snapshot_id == m2v_result.snapshot_id
    assert hgt_result.metadata["graph_fingerprint"] == m2v_result.metadata["graph_fingerprint"]
    assert set(m2v_result.nodes["node_id"]) <= set(hgt_result.nodes["node_id"])


def test_metrics_helpers():
    labels = np.array([1, 1, 0, 0])
    assert hgt.roc_auc(labels, np.array([0.9, 0.8, 0.1, 0.2])) == 1.0
    assert hgt.roc_auc(labels, np.array([0.1, 0.2, 0.9, 0.8])) == 0.0
    assert hgt.average_precision(labels, np.array([0.9, 0.8, 0.1, 0.2])) == 1.0
    assert hgt.roc_auc(np.array([1, 1]), np.array([0.3, 0.4])) is None
