"""Privacy-safe, aggregate evidence for every ordered channel pair of one scored snapshot.

Sources (all from the SAME research snapshot and ``as_of`` as the scored result):
* STEP 14 features: channel_pair_features (shared commenters, Jaccard, directional overlap) and
  graph_node_features (stored videos, unique commenters, comments per channel).
* The snapshot's comments, aggregated in DuckDB: comments and distinct videos of the pair's shared
  commenters on each channel, and their distinct active days / first / last comment time.
* STEP 19 score rows: topic similarity and topic coverage.

Commenter pseudonyms are used only inside the aggregation query; outputs hold counts only.

Each evidence group carries a state, never conflated:
  observed               evidence exists (value > 0)
  zero                   both channels were observed with commenters and the value is 0
  insufficient_coverage  a channel has no stored videos / no commenters, so absence is not informative
  missing                the input needed for this evidence is not available
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from research.component_3.preprocessing import graph_features as gf
from research.component_3.preprocessing import hetero_graph as hg
from research.component_3.preprocessing import research_dataset as rd

OBSERVED, ZERO, INSUFFICIENT, MISSING = "observed", "zero", "insufficient_coverage", "missing"
NOT_USED = "not_used"   # the scoring experiment has no embedding component (w_embedding = 0)
EVIDENCE_COLUMNS = {
    "source_channel_id": "string", "destination_channel_id": "string",
    "source_stored_videos": "Int64", "destination_stored_videos": "Int64",
    "source_unique_commenters": "Int64", "destination_unique_commenters": "Int64",
    "source_comments": "Int64", "destination_comments": "Int64",
    "shared_commenters": "Int64", "jaccard_similarity": "Float64",
    "directional_overlap_source_to_destination": "Float64", "shared_commenter_state": "string",
    "shared_comments_on_source": "Int64", "shared_comments_on_destination": "Int64",
    "shared_videos_on_source": "Int64", "shared_videos_on_destination": "Int64",
    "source_video_coverage": "Float64", "destination_video_coverage": "Float64", "video_coverage_state": "string",
    "shared_active_days": "Int64", "shared_first_comment_at": "datetime64[us, UTC]",
    "shared_last_comment_at": "datetime64[us, UTC]", "shared_span_days": "Float64", "temporal_state": "string",
    "topic_similarity": "Float64", "source_topic_coverage": "Float64", "destination_topic_coverage": "Float64",
    "topic_state": "string", "embedding_similarity": "Float64", "embedding_state": "string",
    "snapshot_id": "string", "as_of": "datetime64[us, UTC]",
}


def load_feature_set(snapshot_id: str, as_of: datetime, graph: hg.HeteroGraph) -> gf.FeatureSet:
    path = gf.features_dir(snapshot_id, as_of)
    return gf.load_features(path) if (path / gf.MANIFEST_FILE).is_file() else \
        gf.build_features(snapshot_id, as_of=as_of, graph=graph)


def shared_activity(snapshot_id: str, as_of: datetime) -> pd.DataFrame:
    """Per ordered pair: aggregate activity of commenters who commented on both channels (as of)."""
    lit = f"TIMESTAMPTZ '{as_of.isoformat()}'"
    sql = f"""
    WITH cc AS (SELECT author_channel_id AS a, 'channel:' || channel_id AS ch, video_id, published_at
                FROM comments WHERE published_at <= {lit} AND author_channel_id IS NOT NULL),
         ac AS (SELECT DISTINCT a, ch FROM cc),
         sp AS (SELECT x.ch AS src, y.ch AS dst, x.a FROM ac x JOIN ac y ON x.a = y.a AND x.ch <> y.ch)
    SELECT sp.src AS source_channel_id, sp.dst AS destination_channel_id,
           count(*) FILTER (WHERE cc.ch = sp.src) AS shared_comments_on_source,
           count(*) FILTER (WHERE cc.ch = sp.dst) AS shared_comments_on_destination,
           count(DISTINCT cc.video_id) FILTER (WHERE cc.ch = sp.src) AS shared_videos_on_source,
           count(DISTINCT cc.video_id) FILTER (WHERE cc.ch = sp.dst) AS shared_videos_on_destination,
           count(DISTINCT CAST(cc.published_at AT TIME ZONE 'UTC' AS DATE)) AS shared_active_days,
           min(cc.published_at) AS shared_first_comment_at, max(cc.published_at) AS shared_last_comment_at
    FROM sp JOIN cc ON cc.a = sp.a AND cc.ch IN (sp.src, sp.dst)
    GROUP BY sp.src, sp.dst ORDER BY 1, 2"""
    with rd.research_session(snapshot_id) as con:
        return con.execute(sql).df()


def build_evidence(scores: pd.DataFrame, snapshot_id: str, as_of: datetime, graph: hg.HeteroGraph,
                   features: gf.FeatureSet | None = None, embedding_used: bool = False) -> pd.DataFrame:
    """Evidence rows for the (source, destination) pairs of ``scores`` (a STEP 19 score table)."""
    if features is None:
        features = load_feature_set(snapshot_id, as_of, graph)
    if features.snapshot_id != snapshot_id or features.as_of != as_of:
        raise ValueError("features come from a different snapshot or as_of than the scored result")
    pairs = scores[["source_channel_id", "destination_channel_id", "raw_topic_similarity", "source_topic_coverage",
                    "destination_topic_coverage", "raw_embedding_similarity"]].rename(
        columns={"raw_topic_similarity": "topic_similarity", "raw_embedding_similarity": "embedding_similarity"})
    if pairs.empty:
        return pd.DataFrame(columns=list(EVIDENCE_COLUMNS)).astype(EVIDENCE_COLUMNS)

    nodes = features["graph_node_features"]
    nodes = nodes[nodes["node_type"] == "channel"].set_index("node_id")
    df = pairs.copy()
    for side, col in (("source", "source_channel_id"), ("destination", "destination_channel_id")):
        df[f"{side}_stored_videos"] = df[col].map(nodes["stored_video_count"])
        df[f"{side}_unique_commenters"] = df[col].map(nodes["unique_commenter_count"])
        df[f"{side}_comments"] = df[col].map(nodes["comment_count"])

    pf = features["channel_pair_features"]
    fwd = pf.rename(columns={"channel_a": "source_channel_id", "channel_b": "destination_channel_id",
                             "directional_overlap_a_to_b": "directional_overlap_source_to_destination"})
    rev = pf.rename(columns={"channel_b": "source_channel_id", "channel_a": "destination_channel_id",
                             "directional_overlap_b_to_a": "directional_overlap_source_to_destination"})
    cols = ["source_channel_id", "destination_channel_id", "shared_commenter_count", "jaccard_similarity",
            "directional_overlap_source_to_destination"]
    df = df.merge(pd.concat([fwd[cols], rev[cols]]), how="left", on=["source_channel_id", "destination_channel_id"])
    df = df.rename(columns={"shared_commenter_count": "shared_commenters"})
    df = df.merge(shared_activity(snapshot_id, as_of), how="left", on=["source_channel_id", "destination_channel_id"])

    observed = (df["source_unique_commenters"].fillna(0) > 0) & (df["destination_unique_commenters"].fillna(0) > 0)
    no_videos = (df["source_stored_videos"].fillna(0) == 0) | (df["destination_stored_videos"].fillna(0) == 0)
    has_shared = df["shared_commenters"].fillna(0) > 0
    # absent pair rows mean no shared commenter: a true zero only when both channels were observed
    zero_fill = ["shared_commenters", "jaccard_similarity", "directional_overlap_source_to_destination",
                 "shared_comments_on_source", "shared_comments_on_destination", "shared_videos_on_source",
                 "shared_videos_on_destination", "shared_active_days"]
    for c in zero_fill:
        df[c] = df[c].astype("Float64").where(df[c].notna() | ~observed, 0.0)
    df["shared_commenter_state"] = _state(has_shared, observed)

    df["source_video_coverage"] = _ratio(df["shared_videos_on_source"], df["source_stored_videos"])
    df["destination_video_coverage"] = _ratio(df["shared_videos_on_destination"], df["destination_stored_videos"])
    df["video_coverage_state"] = _state(has_shared, observed & ~no_videos)
    df.loc[no_videos, "video_coverage_state"] = INSUFFICIENT

    span = (pd.to_datetime(df["shared_last_comment_at"], utc=True) -
            pd.to_datetime(df["shared_first_comment_at"], utc=True)).dt.total_seconds() / 86400
    df["shared_span_days"] = span.astype("Float64")
    df["temporal_state"] = _state(has_shared, observed)

    topic_ok = df["topic_similarity"].notna() & df["source_topic_coverage"].notna() & \
        df["destination_topic_coverage"].notna()
    df["topic_state"] = [OBSERVED if ok else MISSING for ok in topic_ok]
    df["embedding_state"] = [NOT_USED if not embedding_used else OBSERVED if pd.notna(v) else MISSING
                             for v in df["embedding_similarity"]]
    df = df.assign(snapshot_id=snapshot_id, as_of=pd.Timestamp(as_of))
    return df[list(EVIDENCE_COLUMNS)].astype(EVIDENCE_COLUMNS).reset_index(drop=True)


def _state(has: pd.Series, observed: pd.Series) -> list[str]:
    return [OBSERVED if h else ZERO if o else INSUFFICIENT for h, o in zip(has, observed)]


def _ratio(num: pd.Series, den: pd.Series) -> pd.Series:
    n, d = num.astype("Float64"), den.astype("Float64")
    return (n / d.where(d > 0)).astype("Float64")
