"""Component 3 graph features and transparent edge weighting (descriptive, not scores).

    python -m research.component_3.preprocessing.graph_features                       # latest snapshot, as of extraction
    python -m research.component_3.preprocessing.graph_features --as-of 2026-10-01T00:00:00Z

Enriches the STEP 13 heterogeneous graph with deterministic features computed by
DuckDB SQL from the research snapshot's event-level data, as of a reference time
``as_of`` (default: the snapshot's extraction time):

  * only comments / videos published at or before ``as_of`` are used;
  * public metrics (views, likes, subscribers, API counts) are observations made at
    collection time; they are used only if collected at or before ``as_of``,
    otherwise NULL ("not observed as of") - no future information leaks in.

Artifacts: data/processed/component_3/<snapshot_id>/features/asof-<YYYYMMDDTHHMMSSZ>/
  graph_node_features, graph_edge_features, channel_pair_features,
  commenter_channel_features (.parquet) + feature_manifest.json

These are DESCRIPTIVE features and baseline measures. They are not diffusion
scores, topic similarity, confidence weights or Audience Bridge Scores.
Commenters appear only as pseudonyms; overlap is an interaction signal, not
audience migration.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from research.component_3.preprocessing import hetero_graph as hg
from research.component_3.preprocessing import research_dataset as rd
from shared.utils import snapshots
from shared.utils.parquet_io import read_dataset, write_dataset

FEATURE_SCHEMA_VERSION = "1.0"
FEATURES_DIR = "features"
MANIFEST_FILE = "feature_manifest.json"
TS = "datetime64[us, UTC]"

NODE_FEATURE_COLUMNS = {
    "node_id": "string", "node_type": "string", "snapshot_id": "string", "as_of": TS,
    # A. structural
    "stored_video_count": "Int64", "unique_commenter_count": "Int64", "channel_count": "Int64", "video_count": "Int64",
    # B. interaction
    "comment_count": "Int64", "reply_count": "Int64", "avg_comments_per_video": "float64",
    "median_comments_per_video": "float64", "active_commenter_count": "Int64", "interaction_density": "float64",
    "is_cross_channel": "boolean",
    # public metrics observed at collection time (NULL if hidden or not observed as of)
    "observed_subscriber_count": "Int64", "observed_view_count": "Int64", "observed_like_count": "Int64",
    "observed_api_comment_count": "Int64", "observed_api_video_count": "Int64",
    "comments_per_view": "float64", "likes_per_view": "float64",
    # C. temporal
    "published_at": TS, "age_days": "float64", "first_interaction_at": TS, "last_interaction_at": TS,
    "active_span_days": "float64", "days_since_first_interaction": "float64", "recency_days": "float64",
    "active_days": "Int64", "comments_per_active_day": "float64",
    # F. data coverage / support (evidence indicators, not confidence scores)
    "collection_coverage": "float64", "interaction_support_count": "Int64",
}
EDGE_FEATURE_COLUMNS = {
    "source_node_id": "string", "target_node_id": "string", "edge_type": "string",
    "snapshot_id": "string", "as_of": TS,
    "comment_count": "Int64", "reply_count": "Int64", "video_count": "Int64",
    "first_at": TS, "last_at": TS, "active_span_days": "float64",
    "interaction_weight": "float64", "channel_share": "float64",
}
PAIR_FEATURE_COLUMNS = {
    "channel_a": "string", "channel_b": "string", "snapshot_id": "string", "as_of": TS,
    "shared_commenter_count": "Int64", "channel_a_unique_commenter_count": "Int64",
    "channel_b_unique_commenter_count": "Int64", "union_commenter_count": "Int64",
    "jaccard_similarity": "float64", "directional_overlap_a_to_b": "float64",
    "directional_overlap_b_to_a": "float64", "overlap_ratio": "float64",
}
COMMENTER_CHANNEL_COLUMNS = {
    "commenter_id": "string", "channel_id": "string", "snapshot_id": "string", "as_of": TS,
    "video_count": "Int64", "comment_count": "Int64", "reply_count": "Int64",
    "first_interaction_at": TS, "last_interaction_at": TS, "active_span_days": "float64",
    "interaction_weight": "float64",
}
TABLES = {
    "graph_node_features": (NODE_FEATURE_COLUMNS, ["node_id"]),
    "graph_edge_features": (EDGE_FEATURE_COLUMNS, ["edge_type", "source_node_id", "target_node_id"]),
    "channel_pair_features": (PAIR_FEATURE_COLUMNS, ["channel_a", "channel_b"]),
    "commenter_channel_features": (COMMENTER_CHANNEL_COLUMNS, ["commenter_id", "channel_id"]),
}
# Ratios that must lie in [0, 1] (validated, never clipped).
UNIT_RATIOS = {
    "graph_edge_features": ["channel_share"],
    "channel_pair_features": ["jaccard_similarity", "directional_overlap_a_to_b", "directional_overlap_b_to_a",
                              "overlap_ratio"],
}
NON_NEGATIVE = ["stored_video_count", "unique_commenter_count", "channel_count", "video_count", "comment_count",
                "reply_count", "active_commenter_count", "observed_subscriber_count", "observed_view_count",
                "observed_like_count", "observed_api_comment_count", "observed_api_video_count",
                "active_days", "interaction_support_count", "shared_commenter_count",
                "channel_a_unique_commenter_count", "channel_b_unique_commenter_count", "union_commenter_count",
                "age_days", "active_span_days", "days_since_first_interaction", "recency_days",
                "comments_per_view", "likes_per_view", "interaction_density", "comments_per_active_day",
                "avg_comments_per_video", "median_comments_per_video", "collection_coverage", "interaction_weight"]

FORMULAS = {
    "interaction_weight": "ln(1 + comment_count) (commenter->video and commenter->channel edges)",
    "channel_share": "commenter's comments on the channel / commenter's total comments (as of)",
    "jaccard_similarity": "|A ∩ B| / |A ∪ B| over the two channels' commenter sets",
    "directional_overlap_a_to_b": "|A ∩ B| / |A| (directional: share of A's commenters also on B)",
    "directional_overlap_b_to_a": "|A ∩ B| / |B|",
    "overlap_ratio": "|A ∩ B| / min(|A|, |B|) (overlap coefficient)",
    "avg_comments_per_video": "channel comment_count / stored_video_count",
    "median_comments_per_video": "median stored comments over the channel's stored videos (videos with 0 count as 0)",
    "active_commenter_count": "commenters with at least 2 comments on the channel",
    "interaction_density": "video: stored comments / unique commenters",
    "comments_per_view": "observed API comment count / observed view count",
    "likes_per_view": "observed like count / observed view count",
    "age_days": "(as_of - published_at) in days",
    "active_span_days": "(last - first interaction) in days",
    "days_since_first_interaction": "(as_of - first interaction) in days",
    "recency_days": "(as_of - last interaction) in days",
    "active_days": "distinct UTC calendar days with at least one comment",
    "comments_per_active_day": "comment_count / active_days",
    "collection_coverage": "channel: stored videos / observed API video count; "
                           "video: stored comments / observed API comment count (not bounded: API counts can lag)",
    "interaction_support_count": "number of observed comments behind the node's interaction features",
}
MISSING_VALUE_POLICY = {
    "not_applicable": "NULL for feature columns that do not apply to the node / edge type",
    "unavailable": "NULL when YouTube hides the value (e.g. hidden likes, disabled comments)",
    "not_observed_as_of": "NULL for public metrics collected after as_of (no future information)",
    "undefined_ratio": "NULL when a ratio's denominator is 0 or NULL (never 0 or infinity)",
    "zero": "0 only for genuinely counted zero (e.g. a stored video with no stored comments)",
}


class FeatureValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("feature validation failed:\n- " + "\n- ".join(errors))


@dataclass
class FeatureSet:
    snapshot_id: str
    as_of: datetime
    tables: dict[str, pd.DataFrame]
    manifest: dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, name: str) -> pd.DataFrame:
        return self.tables[name]

    def fingerprint(self) -> str:
        digest = hashlib.sha256()
        for name in TABLES:
            digest.update(name.encode())
            digest.update(self.tables[name].to_csv(index=False, date_format="%Y-%m-%dT%H:%M:%S.%fZ").encode())
        return digest.hexdigest()


# --- construction --------------------------------------------------------------------------

def build_features(snapshot_id: str, *, as_of: datetime | None = None,
                   graph: hg.HeteroGraph | None = None) -> FeatureSet:
    """Compute all feature tables of a snapshot as of ``as_of`` and validate them against the graph."""
    info = snapshots.get_research_snapshot(snapshot_id)
    snapshot_time = _snapshot_time(info)
    as_of = (as_of or snapshot_time)
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    as_of = as_of.astimezone(timezone.utc)
    if as_of > snapshot_time:
        raise ValueError(f"as_of {as_of.isoformat()} is after the snapshot ({snapshot_time.isoformat()}): "
                         "nothing after the snapshot is known")
    graph = graph or _graph_for(info.snapshot_id)

    lit = f"TIMESTAMPTZ '{as_of.isoformat()}'"
    with rd.research_session(info.snapshot_id) as con:
        con.execute(f"CREATE TEMP VIEW f_videos AS SELECT * FROM videos WHERE published_at <= {lit}")
        con.execute(f"""CREATE TEMP VIEW f_all_comments AS SELECT c.*, v.channel_id AS video_channel_id
                        FROM comments c JOIN f_videos v USING (video_id) WHERE c.published_at <= {lit}""")
        con.execute("CREATE TEMP VIEW f_comments AS SELECT * FROM f_all_comments WHERE author_channel_id IS NOT NULL")
        node_parts = [con.execute(sql.replace("{AS_OF}", lit)).df() for sql in (_CHANNEL_SQL, _VIDEO_SQL, _COMMENTER_SQL)]
        edges = con.execute(_EDGE_SQL.replace("{AS_OF}", lit)).df()
        pairs = con.execute(_PAIR_SQL).df()
        coverage = {k: int(con.execute(f"SELECT count(*) FROM {v}").fetchone()[0]) for k, v in {
            "comment_observation_count": "f_all_comments", "video_observation_count": "f_videos",
            "channel_observation_count": "channels",
            "commenter_observation_count": "(SELECT DISTINCT author_channel_id FROM f_comments)"}.items()}

    common = {"snapshot_id": info.snapshot_id, "as_of": pd.Timestamp(as_of)}
    nodes = pd.concat([p for p in node_parts if len(p)] or [pd.DataFrame(columns=["node_id"])], ignore_index=True)
    participates = edges[edges["edge_type"] == "participates_in"]
    commenter_channel = participates.rename(columns={
        "source_node_id": "commenter_id", "target_node_id": "channel_id",
        "first_at": "first_interaction_at", "last_at": "last_interaction_at"})
    tables = {
        "graph_node_features": _typed(nodes.assign(**common), NODE_FEATURE_COLUMNS),
        "graph_edge_features": _typed(edges.assign(**common), EDGE_FEATURE_COLUMNS),
        "channel_pair_features": _typed(pairs.assign(**common), PAIR_FEATURE_COLUMNS),
        "commenter_channel_features": _typed(commenter_channel.assign(**common), COMMENTER_CHANNEL_COLUMNS),
    }
    tables = {name: _sorted(name, df) for name, df in tables.items()}
    fs = FeatureSet(info.snapshot_id, as_of, tables)
    fs.manifest = {
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "snapshot_id": info.snapshot_id,
        "snapshot_time": snapshot_time.isoformat().replace("+00:00", "Z"),
        "as_of": as_of.isoformat().replace("+00:00", "Z"),
        "snapshot_age_days": round((snapshot_time - as_of).total_seconds() / 86400, 6),
        "graph_fingerprint": graph.fingerprint(),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "row_counts": {n: int(len(df)) for n, df in tables.items()},
        "coverage": coverage,
        "formulas": FORMULAS,
        "missing_value_policy": MISSING_VALUE_POLICY,
        "note": "Descriptive features and baseline measures; not diffusion, topic similarity, "
                "confidence weighting or Audience Bridge Scores.",
    }
    errors = validate_features(fs, graph)
    if errors:
        raise FeatureValidationError(errors)
    return fs


_CHANNEL_SQL = """
WITH vids AS (
    SELECT v.video_id, v.channel_id, coalesce(c.n, 0) AS n
    FROM f_videos v LEFT JOIN (SELECT video_id, count(*) AS n FROM f_all_comments GROUP BY video_id) c USING (video_id)),
v AS (SELECT channel_id, count(*) AS stored_video_count, sum(n) AS comment_count, median(n) AS median_n
      FROM vids GROUP BY channel_id),
r AS (SELECT video_channel_id AS channel_id, count(*) FILTER (WHERE parent_comment_id IS NOT NULL) AS reply_count
      FROM f_all_comments GROUP BY 1),
cm AS (SELECT video_channel_id AS channel_id, count(DISTINCT author_channel_id) AS unique_commenter_count
       FROM f_comments GROUP BY 1),
act AS (SELECT channel_id, count(*) AS active_commenter_count FROM (
            SELECT video_channel_id AS channel_id, author_channel_id FROM f_comments GROUP BY 1, 2 HAVING count(*) >= 2)
        GROUP BY 1)
SELECT 'channel:' || ch.channel_id AS node_id, 'channel' AS node_type,
       coalesce(v.stored_video_count, 0) AS stored_video_count,
       coalesce(cm.unique_commenter_count, 0) AS unique_commenter_count,
       coalesce(v.comment_count, 0) AS comment_count, coalesce(r.reply_count, 0) AS reply_count,
       v.comment_count / NULLIF(v.stored_video_count, 0) AS avg_comments_per_video,
       v.median_n AS median_comments_per_video,
       coalesce(act.active_commenter_count, 0) AS active_commenter_count,
       CASE WHEN ch.collected_at <= {AS_OF} THEN ch.subscriber_count END AS observed_subscriber_count,
       CASE WHEN ch.collected_at <= {AS_OF} THEN ch.view_count END AS observed_view_count,
       CASE WHEN ch.collected_at <= {AS_OF} THEN ch.video_count END AS observed_api_video_count,
       ch.published_at,
       epoch({AS_OF} - ch.published_at) / 86400.0 AS age_days,
       coalesce(v.stored_video_count, 0)
           / NULLIF(CASE WHEN ch.collected_at <= {AS_OF} THEN ch.video_count END, 0) AS collection_coverage,
       coalesce(v.comment_count, 0) AS interaction_support_count
FROM channels ch
LEFT JOIN v USING (channel_id) LEFT JOIN r USING (channel_id)
LEFT JOIN cm USING (channel_id) LEFT JOIN act USING (channel_id)
WHERE ch.published_at IS NULL OR ch.published_at <= {AS_OF}
"""

_VIDEO_SQL = """
WITH c AS (SELECT video_id, count(*) AS n, count(*) FILTER (WHERE parent_comment_id IS NOT NULL) AS replies,
                  count(DISTINCT author_channel_id) AS commenters
           FROM f_all_comments GROUP BY video_id)
SELECT 'video:' || v.video_id AS node_id, 'video' AS node_type,
       coalesce(c.commenters, 0) AS unique_commenter_count,
       coalesce(c.n, 0) AS comment_count, coalesce(c.replies, 0) AS reply_count,
       c.n::DOUBLE / NULLIF(c.commenters, 0) AS interaction_density,
       CASE WHEN v.collected_at <= {AS_OF} THEN v.view_count END AS observed_view_count,
       CASE WHEN v.collected_at <= {AS_OF} THEN v.like_count END AS observed_like_count,
       CASE WHEN v.collected_at <= {AS_OF} THEN v.comment_count END AS observed_api_comment_count,
       (CASE WHEN v.collected_at <= {AS_OF} THEN v.comment_count END)::DOUBLE
           / NULLIF(CASE WHEN v.collected_at <= {AS_OF} THEN v.view_count END, 0) AS comments_per_view,
       (CASE WHEN v.collected_at <= {AS_OF} THEN v.like_count END)::DOUBLE
           / NULLIF(CASE WHEN v.collected_at <= {AS_OF} THEN v.view_count END, 0) AS likes_per_view,
       v.published_at,
       epoch({AS_OF} - v.published_at) / 86400.0 AS age_days,
       coalesce(c.n, 0)::DOUBLE
           / NULLIF(CASE WHEN v.collected_at <= {AS_OF} THEN v.comment_count END, 0) AS collection_coverage,
       coalesce(c.n, 0) AS interaction_support_count
FROM f_videos v LEFT JOIN c USING (video_id)
"""

_COMMENTER_SQL = """
SELECT 'commenter:' || author_channel_id AS node_id, 'commenter' AS node_type,
       count(DISTINCT video_channel_id) AS channel_count, count(DISTINCT video_id) AS video_count,
       count(*) AS comment_count, count(*) FILTER (WHERE parent_comment_id IS NOT NULL) AS reply_count,
       count(DISTINCT video_channel_id) > 1 AS is_cross_channel,
       min(published_at) AS first_interaction_at, max(published_at) AS last_interaction_at,
       epoch(max(published_at) - min(published_at)) / 86400.0 AS active_span_days,
       epoch({AS_OF} - min(published_at)) / 86400.0 AS days_since_first_interaction,
       epoch({AS_OF} - max(published_at)) / 86400.0 AS recency_days,
       count(DISTINCT CAST(published_at AS DATE)) AS active_days,
       count(*)::DOUBLE / count(DISTINCT CAST(published_at AS DATE)) AS comments_per_active_day,
       count(*) AS interaction_support_count
FROM f_comments GROUP BY author_channel_id
"""

_EDGE_SQL = """
SELECT 'commenter:' || author_channel_id AS source_node_id, 'video:' || video_id AS target_node_id,
       'comments' AS edge_type, count(*) AS comment_count,
       count(*) FILTER (WHERE parent_comment_id IS NOT NULL) AS reply_count, NULL::BIGINT AS video_count,
       min(published_at) AS first_at, max(published_at) AS last_at,
       epoch(max(published_at) - min(published_at)) / 86400.0 AS active_span_days,
       ln(1 + count(*)) AS interaction_weight, NULL::DOUBLE AS channel_share
FROM f_comments GROUP BY author_channel_id, video_id
UNION ALL
SELECT 'commenter:' || author_channel_id, 'channel:' || video_channel_id, 'participates_in', count(*),
       count(*) FILTER (WHERE parent_comment_id IS NOT NULL), count(DISTINCT video_id),
       min(published_at), max(published_at),
       epoch(max(published_at) - min(published_at)) / 86400.0,
       ln(1 + count(*)),
       count(*)::DOUBLE / sum(count(*)) OVER (PARTITION BY author_channel_id)
FROM f_comments GROUP BY author_channel_id, video_channel_id
"""

_PAIR_SQL = """
WITH cc AS (SELECT DISTINCT author_channel_id AS commenter, video_channel_id AS channel FROM f_comments),
size AS (SELECT channel, count(*) AS n FROM cc GROUP BY channel),
shared AS (SELECT a.channel AS a, b.channel AS b, count(*) AS s
           FROM cc a JOIN cc b ON a.commenter = b.commenter AND a.channel < b.channel GROUP BY 1, 2)
SELECT 'channel:' || shared.a AS channel_a, 'channel:' || shared.b AS channel_b,
       shared.s AS shared_commenter_count, sa.n AS channel_a_unique_commenter_count,
       sb.n AS channel_b_unique_commenter_count, sa.n + sb.n - shared.s AS union_commenter_count,
       shared.s::DOUBLE / NULLIF(sa.n + sb.n - shared.s, 0) AS jaccard_similarity,
       shared.s::DOUBLE / NULLIF(sa.n, 0) AS directional_overlap_a_to_b,
       shared.s::DOUBLE / NULLIF(sb.n, 0) AS directional_overlap_b_to_a,
       shared.s::DOUBLE / NULLIF(least(sa.n, sb.n), 0) AS overlap_ratio
FROM shared JOIN size sa ON sa.channel = shared.a JOIN size sb ON sb.channel = shared.b
"""


# --- validation ------------------------------------------------------------------------------

def validate_features(fs: FeatureSet, graph: hg.HeteroGraph) -> list[str]:
    """Checks against the STEP 13 graph and feature rules. Never clips or repairs."""
    errors: list[str] = []
    as_of = pd.Timestamp(fs.as_of)
    node_types = dict(zip(graph.nodes["node_id"], graph.nodes["node_type"]))
    graph_edges = set(zip(graph.edges["source"], graph.edges["target"], graph.edges["relation"]))

    for name, (columns, key) in TABLES.items():
        df = fs.tables[name]
        if list(df.columns) != list(columns):
            errors.append(f"{name}: columns do not match the feature schema")
            continue
        dupes = int(df.duplicated(key).sum())
        if dupes:
            errors.append(f"{name}: {dupes} duplicate record(s) on {key}")
        if len(df) and ((df["snapshot_id"] != fs.snapshot_id).any() or (df["as_of"] != as_of).any()):
            errors.append(f"{name}: rows with another snapshot_id / as_of")
        for col in [c for c in NON_NEGATIVE if c in df.columns]:
            bad = int((df[col].dropna() < 0).sum())
            if bad:
                errors.append(f"{name}.{col}: {bad} negative value(s)")
        for col in UNIT_RATIOS.get(name, []):
            vals = df[col].dropna()
            bad = int(((vals < 0) | (vals > 1)).sum())
            if bad:
                errors.append(f"{name}.{col}: {bad} value(s) outside [0, 1]")
        for col in [c for c, t in columns.items() if t == TS and c != "as_of"]:
            if (df[col].dropna() > as_of).any():
                errors.append(f"{name}.{col}: timestamps after as_of (future information)")

    n = fs.tables["graph_node_features"]
    unknown = n[~n["node_id"].isin(node_types)]
    if len(unknown):
        errors.append(f"graph_node_features: {len(unknown)} node id(s) not in the graph")
    wrong = n[n["node_id"].isin(node_types) & (n["node_id"].map(node_types) != n["node_type"])]
    if len(wrong):
        errors.append(f"graph_node_features: {len(wrong)} row(s) with a node type different from the graph")
    if len(n) and not n["node_type"].isin(hg.NODE_TYPES).all():
        errors.append("graph_node_features: invalid node types")
    commenters = n.loc[n["node_type"] == "commenter", "node_id"].str.removeprefix("commenter:")
    raw = int((~commenters.str.fullmatch(hg.PSEUDONYM_RE).fillna(False)).sum())
    if raw:
        errors.append(f"graph_node_features: {raw} commenter id(s) are not pseudonyms (values not shown)")

    e = fs.tables["graph_edge_features"]
    if len(e) and not e["edge_type"].isin(["comments", "participates_in"]).all():
        errors.append("graph_edge_features: invalid edge types (only comments / participates_in carry features)")
    missing = [t for t in zip(e["source_node_id"], e["target_node_id"], e["edge_type"]) if t not in graph_edges]
    if missing:
        errors.append(f"graph_edge_features: {len(missing)} edge(s) not in the graph")
    if len(e) and (e["first_at"] > e["last_at"]).any():
        errors.append("graph_edge_features: first_at after last_at")
    expected_w = e["comment_count"].astype("float64").map(math.log1p)
    if len(e) and (abs(e["interaction_weight"] - expected_w) > 1e-12).any():
        errors.append("graph_edge_features: interaction_weight is not ln(1 + comment_count)")

    p = fs.tables["channel_pair_features"]
    if len(p) and (p["channel_a"] >= p["channel_b"]).any():
        errors.append("channel_pair_features: pairs must be ordered channel_a < channel_b")
    if len(p) and not (p["channel_a"].isin(node_types) & p["channel_b"].isin(node_types)).all():
        errors.append("channel_pair_features: channels not in the graph")
    if len(p) and (p["shared_commenter_count"] > p[["channel_a_unique_commenter_count",
                                                  "channel_b_unique_commenter_count"]].min(axis=1)).any():
        errors.append("channel_pair_features: shared count exceeds a channel's commenter count")
    return errors


# --- storage ---------------------------------------------------------------------------

def features_dir(snapshot_id: str, as_of: datetime) -> Path:
    tag = "asof-" + as_of.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return hg.graph_dir(snapshot_id).parent / FEATURES_DIR / tag


def save_features(fs: FeatureSet, directory: Path | None = None) -> Path:
    """Write the feature tables once; an identical existing set is accepted, a different one refused."""
    target = directory or features_dir(fs.snapshot_id, fs.as_of)
    if (target / MANIFEST_FILE).is_file():
        existing = json.loads((target / MANIFEST_FILE).read_text(encoding="utf-8"))
        if existing.get("fingerprint") == fs.fingerprint():
            return target
        raise FileExistsError(f"different features already exist at {target}")
    staging = target.with_name(f".{target.name}.staging")
    for name, df in fs.tables.items():
        write_dataset(df, staging / f"{name}.parquet", overwrite=True)
    manifest = {**fs.manifest, "fingerprint": fs.fingerprint()}
    (staging / MANIFEST_FILE).write_text(json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging, target)
    return target


def load_features(directory: Path) -> FeatureSet:
    manifest = json.loads((directory / MANIFEST_FILE).read_text(encoding="utf-8"))
    tables = {name: _sorted(name, _typed(read_dataset(directory / f"{name}.parquet"), cols))
              for name, (cols, _) in TABLES.items()}
    fs = FeatureSet(manifest["snapshot_id"], datetime.fromisoformat(manifest["as_of"].replace("Z", "+00:00")),
                    tables, manifest)
    if fs.fingerprint() != manifest.get("fingerprint"):
        raise FeatureValidationError(["feature files changed after they were saved (fingerprint mismatch)"])
    return fs


# --- helpers -----------------------------------------------------------------------------

def _snapshot_time(info) -> datetime:
    value = info.manifest.get("extracted_at") or info.manifest["created_at"]
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _graph_for(snapshot_id: str) -> hg.HeteroGraph:
    path = hg.graph_dir(snapshot_id)
    if (path / hg.MANIFEST_FILE).is_file():
        return hg.load_graph(path)
    graph = hg.build_graph(snapshot_id)
    hg.save_graph(graph)
    return graph


def _typed(df: pd.DataFrame, columns: dict[str, str]) -> pd.DataFrame:
    df = df.reindex(columns=list(columns))
    for col, dtype in columns.items():
        if dtype == TS:
            df[col] = pd.to_datetime(df[col], utc=True).astype(TS)
        elif dtype == "boolean":
            df[col] = df[col].astype("boolean")
        else:
            df[col] = df[col].astype(dtype)
    return df


def _sorted(name: str, df: pd.DataFrame) -> pd.DataFrame:
    key = TABLES[name][1]
    if name == "graph_node_features":
        order = df["node_type"].map({t: i for i, t in enumerate(hg.NODE_TYPES)})
        return df.assign(_o=order).sort_values(["_o", "node_id"], kind="stable").drop(columns="_o").reset_index(drop=True)
    return df.sort_values(key, kind="stable").reset_index(drop=True)


# --- command line ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="graph_features", description="Build Component 3 graph features.")
    parser.add_argument("--snapshot", help="research snapshot id (default: latest)")
    parser.add_argument("--as-of", help="reference time, ISO 8601 with time zone (default: snapshot extraction time)")
    args = parser.parse_args(argv)
    try:
        sid = args.snapshot or snapshots.latest_research_snapshot().snapshot_id
        as_of = datetime.fromisoformat(args.as_of.replace("Z", "+00:00")) if args.as_of else None
        fs = build_features(sid, as_of=as_of)
        path = save_features(fs)
    except (ValueError, FileExistsError, hg.GraphBuildError, snapshots.SnapshotNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    m = fs.manifest
    print(f"Features for snapshot {sid} as of {m['as_of']} saved to {path}")
    print("  rows: " + ", ".join(f"{k} {v}" for k, v in m["row_counts"].items()))
    print("  coverage: " + ", ".join(f"{k} {v}" for k, v in m["coverage"].items()))
    top = fs["channel_pair_features"].sort_values(["jaccard_similarity", "channel_a"], ascending=[False, True]).head(5)
    for r in top.itertuples():
        print(f"    {r.channel_a} <-> {r.channel_b}: shared {r.shared_commenter_count}, "
              f"Jaccard {r.jaccard_similarity:.4f}, A->B {r.directional_overlap_a_to_b:.4f}, "
              f"B->A {r.directional_overlap_b_to_a:.4f}")
    print("  (descriptive features and baseline measures only; no Audience Bridge Score)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
