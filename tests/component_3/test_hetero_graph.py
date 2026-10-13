"""Tests for the Component 3 heterogeneous graph.

TEST DATA (synthetic, from the step specification):
  channels A, B, C; videos A1, A2 (A), B1 (B), C1 (C); commenters P1, P2, P3
  P1 -> A1 (3 comments: 2 top-level + 1 reply), P1 -> B1
  P2 -> A2
  P3 -> B1, P3 -> C1
Commenter ids are pseudonymized with a test salt; raw values are never printed.
"""

import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from research.component_3.preprocessing import hetero_graph as hg
from shared.schemas import Channel, Comment, Video, to_dataframe
from shared.utils import privacy
from shared.utils import snapshots as s

T = datetime(2026, 9, 30, 8, 0, tzinfo=timezone.utc)
SALT = b"test-salt-" + b"0" * 54
RAW = {"P1": "UC_raw_graph_P1_xxxx", "P2": "UC_raw_graph_P2_xxxx", "P3": "UC_raw_graph_P3_xxxx"}
P = {k: privacy.pseudonymize_id(v, SALT) for k, v in RAW.items()}
CH = {"A": "UC_test_A", "B": "UC_test_B", "C": "UC_test_C"}


def channels():
    return [Channel(channel_id=c, channel_name=f"Channel {k}", published_at="2015-01-01T00:00:00Z",
                    subscriber_count=1000, view_count=50, video_count=2, collected_at=T) for k, c in CH.items()]


def videos():
    rows = [("A1", "A"), ("A2", "A"), ("B1", "B"), ("C1", "C")]
    return [Video(video_id=v, channel_id=CH[c], title=f"Video {v}", published_at="2026-09-01T10:00:00Z",
                  duration_seconds=120, view_count=100, like_count=5, comment_count=3, collected_at=T)
            for v, c in rows]


def comment(cid, vid, ch, who, day, parent=None):
    at = f"2026-09-{day:02d}T10:00:00Z"
    return Comment(comment_id=cid, video_id=vid, channel_id=CH[ch], author_channel_id=P[who] if who else None,
                   comment_text="Synthetic.", published_at=at, edited_at=at, parent_comment_id=parent, collected_at=T)


def comments():
    return [
        comment("k1", "A1", "A", "P1", 5),
        comment("k2", "A1", "A", "P1", 7),
        comment("k1.r1", "A1", "A", "P1", 8, parent="k1"),
        comment("k3", "B1", "B", "P1", 6),
        comment("k4", "A2", "A", "P2", 9),
        comment("k5", "B1", "B", "P3", 10),
        comment("k6", "C1", "C", "P3", 11),
        comment("k7", "C1", "C", None, 12),  # no commenter id: no commenter node / edge
    ]


@pytest.fixture
def ticking(monkeypatch):
    times = iter(datetime(2026, 10, 8, 10, 0, tzinfo=timezone.utc) + timedelta(seconds=i) for i in range(100))
    monkeypatch.setattr(s, "_utcnow", lambda: next(times))


def snapshot(co=None, vi=None):
    frames = {"channels": to_dataframe(channels(), Channel),
              "videos": to_dataframe(vi if vi is not None else videos(), Video),
              "comments": to_dataframe(co if co is not None else comments(), Comment)}
    return s.create_research_snapshot(frames, source="synthetic_test").snapshot_id


@pytest.fixture
def graph(isolated_data_dir, ticking):
    return hg.build_graph(snapshot())


def edge(g, rel, src, dst):
    e = g.edges_of(rel)
    hit = e[(e.source == src) & (e.target == dst)]
    assert len(hit) == 1, (rel, src, dst)
    return hit.iloc[0]


# --- nodes -------------------------------------------------------------------------------

def test_node_types_and_ids(graph):
    assert graph.manifest["statistics"]["node_counts"] == {"channel": 3, "video": 4, "commenter": 3, "topic": 0}
    assert set(graph.nodes_of("channel")["node_id"]) == {f"channel:{c}" for c in CH.values()}
    assert set(graph.nodes_of("video")["node_id"]) == {"video:A1", "video:A2", "video:B1", "video:C1"}
    assert set(graph.nodes_of("commenter")["node_id"]) == {f"commenter:{p}" for p in P.values()}
    v = graph.nodes_of("video").set_index("key").loc["A1"]
    assert v["channel_id"] == CH["A"] and v["duration_seconds"] == 120 and v["label"] == "Video A1"
    assert v["published_at"] == pd.Timestamp("2026-09-01T10:00:00Z")
    c = graph.nodes_of("commenter").iloc[0]
    assert pd.isna(c["label"]) and pd.isna(c["published_at"])  # minimal commenter attributes


def test_topic_types_present_but_empty(graph):
    assert graph.nodes_of("topic").empty and graph.edges_of("has_topic").empty
    assert "has_topic" in graph.manifest["relations"] and "topic" in graph.manifest["node_types"]


# --- edges -------------------------------------------------------------------------------

def test_edge_types_and_counts(graph):
    assert graph.manifest["statistics"]["edge_counts"] == {
        "comments": 5, "belongs_to": 4, "participates_in": 5, "has_topic": 0}
    assert set(graph.edges["relation"]) == {"comments", "belongs_to", "participates_in"}
    e = edge(graph, "belongs_to", "video:B1", f"channel:{CH['B']}")
    assert e["weight"] == 1.0 and e["source_type"] == "video" and e["target_type"] == "channel"


def test_multiple_comments_aggregate_into_one_weighted_edge(graph):
    e = edge(graph, "comments", f"commenter:{P['P1']}", "video:A1")
    assert e["weight"] == 3.0 and e["comment_count"] == 3 and e["reply_count"] == 1
    assert e["first_at"] == pd.Timestamp("2026-09-05T10:00:00Z")
    assert e["last_at"] == pd.Timestamp("2026-09-08T10:00:00Z")
    assert not e["derived"]


def test_channel_participation(graph):
    part = graph.edges_of("participates_in")
    got = {(r.source, r.target) for r in part.itertuples()}
    assert got == {
        (f"commenter:{P['P1']}", f"channel:{CH['A']}"), (f"commenter:{P['P1']}", f"channel:{CH['B']}"),
        (f"commenter:{P['P2']}", f"channel:{CH['A']}"),
        (f"commenter:{P['P3']}", f"channel:{CH['B']}"), (f"commenter:{P['P3']}", f"channel:{CH['C']}"),
    }
    a = edge(graph, "participates_in", f"commenter:{P['P1']}", f"channel:{CH['A']}")
    assert a["weight"] == 3.0 and a["video_count"] == 1 and a["derived"]
    assert a["first_at"] == pd.Timestamp("2026-09-05T10:00:00Z") and a["last_at"] == pd.Timestamp("2026-09-08T10:00:00Z")


def test_shared_commenters(graph):
    st = graph.manifest["statistics"]
    assert st["commenters_on_multiple_channels"] == 2  # P1 (A,B), P3 (B,C)
    assert st["top_channel_pairs"] == [
        {"channel_a": f"channel:{CH['A']}", "channel_b": f"channel:{CH['B']}", "shared_commenters": 1},
        {"channel_a": f"channel:{CH['B']}", "channel_b": f"channel:{CH['C']}", "shared_commenters": 1},
    ]
    assert st["unique_commenters"] == 3 and st["unique_channels"] == 3 and st["unique_videos"] == 4
    assert st["total_nodes"] == 10 and st["total_edges"] == 14 and st["total_edges_excluding_derived"] == 9


# --- determinism / serialization ---------------------------------------------------------------

def test_deterministic(isolated_data_dir, ticking):
    sid = snapshot()
    a, b = hg.build_graph(sid), hg.build_graph(sid)
    pd.testing.assert_frame_equal(a.nodes, b.nodes)
    pd.testing.assert_frame_equal(a.edges, b.edges)
    assert a.fingerprint() == b.fingerprint()
    other = hg.build_graph(snapshot())  # same data in another snapshot -> same graph content
    assert other.fingerprint() == a.fingerprint()


def test_save_and_load_round_trip(graph):
    path = hg.save_graph(graph)
    assert {p.name for p in path.iterdir()} == {hg.MANIFEST_FILE, hg.EDGES_FILE, hg.NODES_FILE}
    loaded = hg.load_graph(path)
    pd.testing.assert_frame_equal(loaded.nodes, graph.nodes)
    pd.testing.assert_frame_equal(loaded.edges, graph.edges)
    assert loaded.manifest["weight_definitions"]["comments"].startswith("number of comments")
    assert hg.save_graph(graph) == path  # identical graph: accepted, not rewritten


def test_load_detects_modified_files(graph):
    path = hg.save_graph(graph)
    edges = pd.read_parquet(path / hg.EDGES_FILE)
    edges.loc[0, "weight"] = 99.0
    edges.to_parquet(path / hg.EDGES_FILE, index=False)
    with pytest.raises(hg.GraphValidationError, match="fingerprint"):
        hg.load_graph(path)


def test_different_graph_not_overwritten(graph):
    hg.save_graph(graph)
    changed = hg.HeteroGraph(graph.snapshot_id, graph.nodes, graph.edges.assign(
        weight=graph.edges["weight"].where(graph.edges["relation"] != "belongs_to", 1.0)), graph.manifest)
    changed.nodes = changed.nodes.assign(label=changed.nodes["label"].fillna("x"))
    with pytest.raises(FileExistsError):
        hg.save_graph(changed)


def test_networkx_adapter(graph):
    g = graph.to_networkx()
    assert g.number_of_nodes() == 10 and g.number_of_edges() == 14
    e = g.edges[f"commenter:{P['P1']}", "video:A1"]
    assert e["relation"] == "comments" and e["weight"] == 3.0
    assert g.nodes["video:A1"]["node_type"] == "video"
    assert graph.to_networkx(include_derived=False).number_of_edges() == 9  # no double counting


# --- validation --------------------------------------------------------------------------

def test_valid_graph(graph):
    assert hg.validate_graph(graph) == []


@pytest.mark.parametrize("mutate, expected", [
    (lambda n, e: (pd.concat([n, n.iloc[[0]]]), e), "duplicate node ids"),
    (lambda n, e: (n.assign(node_type=n["node_type"].replace("video", "clip")), e), "invalid node types"),
    (lambda n, e: (n, e.assign(relation=e["relation"].replace("belongs_to", "connected_to"))), "invalid edge types"),
    (lambda n, e: (n[n["node_id"] != "video:C1"], e), "missing nodes"),
    (lambda n, e: (n, e.assign(weight=e["weight"].where(e.index != 0, -1.0))), "non-negative"),
    (lambda n, e: (n, pd.concat([e, e.iloc[[0]]])), "duplicate edge"),
    (lambda n, e: (n, e.assign(target=e["target"].where(e.index != 0, e["source"]))), "self-loop"),
    (lambda n, e: (n, e[~((e.relation == "participates_in") & (e.index == e[e.relation == "participates_in"].index[0]))]),
     "not derivable"),
    (lambda n, e: (n, e[~((e.relation == "belongs_to") & (e.source == "video:A1"))]), "exactly one existing channel"),
])
def test_invalid_graphs_detected(graph, mutate, expected):
    nodes, edges = mutate(graph.nodes.copy(), graph.edges.copy())
    errors = hg.validate_graph(hg.HeteroGraph(graph.snapshot_id, nodes.reset_index(drop=True),
                                              edges.reset_index(drop=True)))
    assert any(expected in err for err in errors), errors
    with pytest.raises(hg.GraphValidationError):
        hg.ensure_valid(hg.HeteroGraph(graph.snapshot_id, nodes.reset_index(drop=True), edges.reset_index(drop=True)))


def test_not_research_ready_snapshot_refused(isolated_data_dir, ticking):
    orphan = comments() + [comment("k9", "Z9", "A", "P2", 13)]  # video Z9 not in the snapshot
    with pytest.raises(hg.GraphBuildError, match="not research-ready"):
        hg.build_graph(snapshot(co=orphan))


# --- privacy -----------------------------------------------------------------------------

def test_no_raw_commenter_ids_in_outputs(graph):
    path = hg.save_graph(graph)
    blob = " ".join([graph.nodes.to_csv(), graph.edges.to_csv(), json.dumps(graph.manifest, default=str)]
                    + [p.read_bytes().decode("latin-1") for p in path.iterdir()])
    for raw in RAW.values():
        assert raw not in blob


def test_raw_commenter_node_rejected(graph):
    nodes = graph.nodes.copy()
    i = nodes.index[nodes.node_type == "commenter"][0]
    nodes.loc[i, ["key", "node_id"]] = ["UC" + "x" * 22, "commenter:UC" + "x" * 22]
    errors = hg.validate_graph(hg.HeteroGraph(graph.snapshot_id, nodes, graph.edges))
    assert any("not pseudonyms" in err for err in errors)


# --- topic hook --------------------------------------------------------------------------

def test_topic_interface_accepts_external_assignments(isolated_data_dir, ticking):
    sid = snapshot()
    topics = pd.DataFrame({"topic_id": ["t_news"], "label": ["TEST topic"]})
    vt = pd.DataFrame({"video_id": ["A1", "B1"], "topic_id": ["t_news", "t_news"], "weight": [0.8, 0.4]})
    g = hg.build_graph(sid, topics=topics, video_topics=vt)
    assert hg.validate_graph(g) == []
    assert set(g.nodes_of("topic")["node_id"]) == {"topic:t_news"}
    assert g.manifest["statistics"]["edge_counts"]["has_topic"] == 2
    with pytest.raises(hg.GraphBuildError):
        hg.build_graph(sid, topics=topics)


# --- CLI -------------------------------------------------------------------------------

def test_cli(isolated_data_dir, ticking, capsys):
    snapshot()
    assert hg.main([]) == 0
    out = capsys.readouterr().out
    assert "commenter 3" in out and "participates_in 5" in out and "no scores" in out
