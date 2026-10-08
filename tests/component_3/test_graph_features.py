"""Tests for Component 3 graph features and edge weighting.

TEST DATA (synthetic):
  channels A, B, C; videos A1, A2 (A), B1 (B), C1 (C)
  commenters: A = {P1, P2}, B = {P1, P3}  ->  Jaccard(A, B) = 1/3, A->B = 1/2, B->A = 1/2
  P1: 2 comments on A1 (one a reply, on two days) + 1 on B1;  P2: 1 on A2;  P3: 1 on B1
  one comment on C1 without a commenter id
Pseudonyms come from a test salt; raw ids are never printed.
"""

import json
import math
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from research.component_3.preprocessing import graph_features as gf
from research.component_3.preprocessing import hetero_graph as hg
from shared.schemas import Channel, Comment, Video, to_dataframe
from shared.utils import privacy
from shared.utils import snapshots as s

COLLECTED = datetime(2026, 9, 30, 8, 0, tzinfo=timezone.utc)
EXTRACTED = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)
SALT = b"test-salt-" + b"0" * 54
RAW = {k: f"UC_raw_feat_{k}_xxxxxxx" for k in ("P1", "P2", "P3")}
P = {k: privacy.pseudonymize_id(v, SALT) for k, v in RAW.items()}
CH = {"A": "UC_test_A", "B": "UC_test_B", "C": "UC_test_C"}


def channels():
    return [Channel(channel_id=CH["A"], channel_name="A", published_at="2016-10-01T00:00:00Z",
                    subscriber_count=1000, view_count=5000, video_count=4, collected_at=COLLECTED),
            Channel(channel_id=CH["B"], channel_name="B", published_at="2020-01-01T00:00:00Z",
                    subscriber_count=None, view_count=100, video_count=0, collected_at=COLLECTED),
            Channel(channel_id=CH["C"], channel_name="C", collected_at=COLLECTED)]


def videos():
    def v(vid, ch, views, likes, comments):
        return Video(video_id=vid, channel_id=CH[ch], title=vid, published_at="2026-09-01T00:00:00Z",
                     view_count=views, like_count=likes, comment_count=comments, collected_at=COLLECTED)
    return [v("A1", "A", 100, 10, 4), v("A2", "A", 0, 0, 1), v("B1", "B", None, None, None), v("C1", "C", 50, 5, 1)]


def comment(cid, vid, ch, who, at, parent=None):
    return Comment(comment_id=cid, video_id=vid, channel_id=CH[ch], author_channel_id=P[who] if who else None,
                   comment_text="Synthetic.", published_at=at, edited_at=at, parent_comment_id=parent,
                   collected_at=COLLECTED)


def comments(extra=()):
    return [comment("k1", "A1", "A", "P1", "2026-09-05T10:00:00Z"),
            comment("k1.r", "A1", "A", "P1", "2026-09-06T10:00:00Z", parent="k1"),
            comment("k2", "B1", "B", "P1", "2026-09-07T10:00:00Z"),
            comment("k3", "A2", "A", "P2", "2026-09-08T10:00:00Z"),
            comment("k4", "B1", "B", "P3", "2026-09-09T10:00:00Z"),
            comment("k5", "C1", "C", None, "2026-09-10T10:00:00Z"), *extra]


@pytest.fixture
def ticking(monkeypatch):
    times = iter(datetime(2026, 10, 8, 11, 0, tzinfo=timezone.utc) + timedelta(seconds=i) for i in range(100))
    monkeypatch.setattr(s, "_utcnow", lambda: next(times))


def snapshot(extra=()):
    frames = {"channels": to_dataframe(channels(), Channel), "videos": to_dataframe(videos(), Video),
              "comments": to_dataframe(comments(extra), Comment)}
    return s.create_research_snapshot(frames, source="synthetic_test", extracted_at=EXTRACTED).snapshot_id


@pytest.fixture
def fs(isolated_data_dir, ticking):
    return gf.build_features(snapshot())


def node(fs, node_id):
    n = fs["graph_node_features"].set_index("node_id")
    return n.loc[node_id]


def edge(fs, etype, src, dst):
    e = fs["graph_edge_features"]
    hit = e[(e.edge_type == etype) & (e.source_node_id == src) & (e.target_node_id == dst)]
    assert len(hit) == 1
    return hit.iloc[0]


# --- schema / defaults ---------------------------------------------------------------------

def test_tables_and_schema(fs):
    assert list(fs.tables) == list(gf.TABLES)
    for name, (cols, _) in gf.TABLES.items():
        assert list(fs[name].columns) == list(cols)
        assert (fs[name]["snapshot_id"] == fs.snapshot_id).all()
    assert fs.as_of == EXTRACTED  # default: snapshot extraction time
    assert gf.validate_features(fs, hg.load_graph(hg.graph_dir(fs.snapshot_id))) == []


# --- channel features --------------------------------------------------------------------

def test_channel_features(fs):
    a = node(fs, f"channel:{CH['A']}")
    assert a["stored_video_count"] == 2 and a["unique_commenter_count"] == 2
    assert a["comment_count"] == 3 and a["reply_count"] == 1
    assert a["avg_comments_per_video"] == 1.5 and a["median_comments_per_video"] == 1.5
    assert a["active_commenter_count"] == 1  # P1 has 2 comments on A
    assert a["observed_subscriber_count"] == 1000 and a["observed_api_video_count"] == 4
    assert a["collection_coverage"] == 0.5  # 2 stored / 4 public videos
    assert a["age_days"] == pytest.approx((EXTRACTED - datetime(2016, 10, 1, tzinfo=timezone.utc)).days)
    b = node(fs, f"channel:{CH['B']}")
    assert pd.isna(b["observed_subscriber_count"])  # hidden: NULL, not 0
    assert pd.isna(b["collection_coverage"])        # API video_count 0: undefined ratio, not inf
    c = node(fs, f"channel:{CH['C']}")
    assert c["unique_commenter_count"] == 0 and c["comment_count"] == 1  # unauthored comment still counted
    assert pd.isna(c["age_days"])  # creation date unknown


# --- video features ----------------------------------------------------------------------

def test_video_features_and_safe_ratios(fs):
    a1 = node(fs, "video:A1")
    assert a1["comment_count"] == 2 and a1["unique_commenter_count"] == 1 and a1["interaction_density"] == 2.0
    assert a1["comments_per_view"] == pytest.approx(4 / 100) and a1["likes_per_view"] == pytest.approx(0.1)
    assert a1["collection_coverage"] == pytest.approx(2 / 4)
    a2 = node(fs, "video:A2")
    assert pd.isna(a2["comments_per_view"]) and pd.isna(a2["likes_per_view"])  # 0 views: undefined, not 0/inf
    b1 = node(fs, "video:B1")
    assert pd.isna(b1["observed_like_count"]) and pd.isna(b1["comments_per_view"])  # hidden metrics
    assert pd.isna(b1["collection_coverage"])
    c1 = node(fs, "video:C1")
    assert c1["unique_commenter_count"] == 0 and pd.isna(c1["interaction_density"])
    assert a1["age_days"] == pytest.approx(30.0)


# --- commenter features ------------------------------------------------------------------

def test_commenter_features(fs):
    p1 = node(fs, f"commenter:{P['P1']}")
    assert (p1["channel_count"], p1["video_count"], p1["comment_count"], p1["reply_count"]) == (2, 2, 3, 1)
    assert bool(p1["is_cross_channel"]) is True
    assert p1["first_interaction_at"] == pd.Timestamp("2026-09-05T10:00:00Z")
    assert p1["last_interaction_at"] == pd.Timestamp("2026-09-07T10:00:00Z")
    assert p1["active_span_days"] == pytest.approx(2.0) and p1["active_days"] == 3
    assert p1["comments_per_active_day"] == pytest.approx(1.0)
    assert p1["recency_days"] == pytest.approx((EXTRACTED - datetime(2026, 9, 7, 10, tzinfo=timezone.utc)).total_seconds() / 86400)
    p2 = node(fs, f"commenter:{P['P2']}")
    assert p2["channel_count"] == 1 and bool(p2["is_cross_channel"]) is False and p2["active_span_days"] == 0


# --- edge features / weights ----------------------------------------------------------------

def test_edge_features_and_log1p_weight(fs):
    e = edge(fs, "comments", f"commenter:{P['P1']}", "video:A1")
    assert e["comment_count"] == 2 and e["reply_count"] == 1
    assert e["interaction_weight"] == pytest.approx(math.log1p(2))
    assert e["active_span_days"] == pytest.approx(1.0) and pd.isna(e["channel_share"])
    pa = edge(fs, "participates_in", f"commenter:{P['P1']}", f"channel:{CH['A']}")
    assert pa["comment_count"] == 2 and pa["video_count"] == 1
    assert pa["interaction_weight"] == pytest.approx(math.log1p(2))
    assert pa["channel_share"] == pytest.approx(2 / 3)
    cc = fs["commenter_channel_features"]
    row = cc[(cc.commenter_id == f"commenter:{P['P1']}") & (cc.channel_id == f"channel:{CH['B']}")].iloc[0]
    assert row["comment_count"] == 1 and row["first_interaction_at"] == pd.Timestamp("2026-09-07T10:00:00Z")
    assert len(cc) == len(fs["graph_edge_features"].query("edge_type == 'participates_in'"))


# --- channel pairs -----------------------------------------------------------------------

def test_channel_pair_overlap_from_specification(fs):
    p = fs["channel_pair_features"]
    assert len(p) == 1  # only observed pairs (A, B); C has no commenters
    r = p.iloc[0]
    assert (r.channel_a, r.channel_b) == (f"channel:{CH['A']}", f"channel:{CH['B']}")
    assert (r.shared_commenter_count, r.channel_a_unique_commenter_count,
            r.channel_b_unique_commenter_count, r.union_commenter_count) == (1, 2, 2, 3)
    assert r.jaccard_similarity == pytest.approx(1 / 3)
    assert r.directional_overlap_a_to_b == pytest.approx(1 / 2)
    assert r.directional_overlap_b_to_a == pytest.approx(1 / 2)
    assert r.overlap_ratio == pytest.approx(1 / 2)


# --- validation --------------------------------------------------------------------------

def _graph(fs):
    return hg.load_graph(hg.graph_dir(fs.snapshot_id))


def test_duplicate_rows_detected(fs):
    t = dict(fs.tables)
    t["channel_pair_features"] = pd.concat([t["channel_pair_features"]] * 2, ignore_index=True)
    errors = gf.validate_features(gf.FeatureSet(fs.snapshot_id, fs.as_of, t), _graph(fs))
    assert any("duplicate record" in e for e in errors)


@pytest.mark.parametrize("table, col, value", [
    ("channel_pair_features", "jaccard_similarity", 1.5),
    ("channel_pair_features", "directional_overlap_a_to_b", -0.1),
    ("graph_edge_features", "channel_share", 2.0),
])
def test_ratio_out_of_range_fails_not_clipped(fs, table, col, value):
    t = {k: v.copy() for k, v in fs.tables.items()}
    idx = t[table][t[table][col].notna()].index[0]
    t[table].loc[idx, col] = value
    errors = gf.validate_features(gf.FeatureSet(fs.snapshot_id, fs.as_of, t), _graph(fs))
    assert any(col in e and "outside [0, 1]" in e for e in errors)
    assert t[table].loc[idx, col] == value  # not clipped


@pytest.mark.parametrize("mutate, message", [
    (lambda t: t["graph_node_features"].assign(node_id=t["graph_node_features"]["node_id"].replace("video:A1", "video:ZZ")),
     "not in the graph"),
    (lambda t: t["graph_node_features"].assign(node_type=t["graph_node_features"]["node_type"].replace("video", "clip")),
     "node type"),
    (lambda t: t["graph_node_features"].assign(comment_count=t["graph_node_features"]["comment_count"] - 100),
     "negative"),
])
def test_invalid_node_features(fs, mutate, message):
    t = dict(fs.tables)
    t["graph_node_features"] = mutate(t)
    errors = gf.validate_features(gf.FeatureSet(fs.snapshot_id, fs.as_of, t), _graph(fs))
    assert any(message in e for e in errors), errors


def test_invalid_edge_features(fs):
    t = {k: v.copy() for k, v in fs.tables.items()}
    e = t["graph_edge_features"]
    e.loc[0, "target_node_id"] = "video:ZZ"
    e.loc[1, "interaction_weight"] = 99.0
    errors = gf.validate_features(gf.FeatureSet(fs.snapshot_id, fs.as_of, t), _graph(fs))
    assert any("not in the graph" in x for x in errors) and any("ln(1 + comment_count)" in x for x in errors)


# --- missing-value policy --------------------------------------------------------------------

def test_missing_value_policy_documented_and_applied(fs):
    assert set(fs.manifest["missing_value_policy"]) == {"not_applicable", "unavailable", "not_observed_as_of",
                                                         "undefined_ratio", "zero"}
    n = fs["graph_node_features"].set_index("node_id")
    assert pd.isna(n.loc[f"commenter:{P['P1']}", "observed_view_count"])   # not applicable
    assert n.loc["video:C1", "unique_commenter_count"] == 0                  # genuine zero
    assert set(fs.manifest["formulas"]) >= {"interaction_weight", "jaccard_similarity", "directional_overlap_a_to_b"}


# --- temporal leakage ---------------------------------------------------------------------

def test_historical_features_do_not_use_future_information(isolated_data_dir, ticking):
    future = [comment("k9", "A1", "A", "P3", "2026-09-25T10:00:00Z")]  # P3 joins A only later
    sid = snapshot(extra=future)
    as_of = datetime(2026, 9, 15, tzinfo=timezone.utc)
    hist = gf.build_features(sid, as_of=as_of)
    full = gf.build_features(sid)

    p3_hist = node(hist, f"commenter:{P['P3']}")
    assert p3_hist["channel_count"] == 1 and p3_hist["comment_count"] == 1
    assert node(full, f"commenter:{P['P3']}")["channel_count"] == 2
    assert hist["channel_pair_features"].iloc[0]["jaccard_similarity"] == pytest.approx(1 / 3)
    assert full["channel_pair_features"].iloc[0]["jaccard_similarity"] == pytest.approx(2 / 3)
    # public metrics were collected after as_of: not observed yet -> NULL, never leaked
    a1 = node(hist, "video:A1")
    assert pd.isna(a1["observed_view_count"]) and pd.isna(a1["comments_per_view"])
    assert pd.isna(node(hist, f"channel:{CH['A']}")["observed_subscriber_count"])
    for name, df in hist.tables.items():
        for col in [c for c, t in gf.TABLES[name][0].items() if t == gf.TS and c != "as_of"]:
            assert (df[col].dropna() <= pd.Timestamp(as_of)).all(), (name, col)


def test_as_of_after_snapshot_rejected(isolated_data_dir, ticking):
    sid = snapshot()
    with pytest.raises(ValueError, match="after the snapshot"):
        gf.build_features(sid, as_of=EXTRACTED + timedelta(days=1))
    with pytest.raises(ValueError, match="timezone"):
        gf.build_features(sid, as_of=datetime(2026, 9, 1))


# --- determinism / storage / privacy -------------------------------------------------------------

def test_deterministic(isolated_data_dir, ticking):
    sid = snapshot()
    a, b = gf.build_features(sid), gf.build_features(sid)
    for name in gf.TABLES:
        pd.testing.assert_frame_equal(a[name], b[name])
    assert a.fingerprint() == b.fingerprint()


def test_save_load_round_trip_and_tamper(fs):
    path = gf.save_features(fs)
    assert path.name == "asof-20261001T000000Z"
    loaded = gf.load_features(path)
    for name in gf.TABLES:
        pd.testing.assert_frame_equal(loaded[name], fs[name])
    assert gf.save_features(fs) == path  # identical: accepted
    df = pd.read_parquet(path / "channel_pair_features.parquet")
    df.loc[0, "jaccard_similarity"] = 0.9
    df.to_parquet(path / "channel_pair_features.parquet", index=False)
    with pytest.raises(gf.FeatureValidationError, match="fingerprint"):
        gf.load_features(path)


def test_no_raw_commenter_ids_in_artifacts(fs):
    path = gf.save_features(fs)
    blob = " ".join([df.to_csv() for df in fs.tables.values()]
                    + [p.read_bytes().decode("latin-1") for p in path.iterdir()] + [json.dumps(fs.manifest)])
    for raw in RAW.values():
        assert raw not in blob


def test_raw_commenter_id_rejected(fs):
    t = {k: v.copy() for k, v in fs.tables.items()}
    n = t["graph_node_features"]
    i = n.index[n.node_type == "commenter"][0]
    n.loc[i, "node_id"] = "commenter:UC" + "x" * 22
    errors = gf.validate_features(gf.FeatureSet(fs.snapshot_id, fs.as_of, t), _graph(fs))
    assert any("not pseudonyms" in e for e in errors)


def test_no_scores_in_outputs(fs):
    cols = {c for df in fs.tables.values() for c in df.columns}
    assert not any(k in c for c in cols for k in ("bridge", "pagerank", "confidence", "topic_similarity"))
    assert "not diffusion" in fs.manifest["note"]


def test_cli(isolated_data_dir, ticking, capsys):
    snapshot()
    assert gf.main([]) == 0
    out = capsys.readouterr().out
    assert "Jaccard 0.3333" in out and "no Audience Bridge Score" in out
