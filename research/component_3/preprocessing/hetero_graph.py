"""Component 3 heterogeneous research graph: commenter - video - channel (- topic).

    python -m research.component_3.preprocessing.hetero_graph                     # latest research snapshot
    python -m research.component_3.preprocessing.hetero_graph --snapshot rs-...

Built from a research-ready STEP 12 snapshot with DuckDB SQL (aggregation in
SQL, assembly in Python). No YouTube calls, no models, no scores.

    Commenter --comments--> Video --belongs_to--> Channel
    Commenter --participates_in--> Channel      (derived from comments + belongs_to)
    Video --has_topic--> Topic                  (schema ready; empty until topic modelling)

Artifact (canonical, deterministic, reloadable):
    data/processed/component_3/<snapshot_id>/graph/graph_nodes.parquet
    data/processed/component_3/<snapshot_id>/graph/graph_edges.parquet
    data/processed/component_3/<snapshot_id>/graph/graph_manifest.json

Commenters are identified only by their pseudonym. A shared commenter is an
observable interaction signal: it does not show audience migration,
subscription, identity or causality.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from research.component_3.preprocessing import research_dataset as rd
from shared.utils import snapshots
from shared.utils.parquet_io import read_dataset, write_dataset
from shared.utils.paths import component_dir
from shared.utils.privacy import HASH_PREFIX

GRAPH_SCHEMA_VERSION = "1.0"
GRAPH_DIR = "graph"
NODES_FILE, EDGES_FILE, MANIFEST_FILE = "graph_nodes.parquet", "graph_edges.parquet", "graph_manifest.json"

NODE_TYPES = ("channel", "video", "commenter", "topic")
# relation -> (source node type, target node type, derived?)
RELATIONS = {
    "comments": ("commenter", "video", False),
    "belongs_to": ("video", "channel", False),
    "participates_in": ("commenter", "channel", True),
    "has_topic": ("video", "topic", False),
}
WEIGHT_DEFINITIONS = {
    "comments": "number of comments (top-level + replies) the commenter posted on the video",
    "belongs_to": "1.0 (structural membership of a video in its channel)",
    "participates_in": "number of comments the commenter posted across all videos of the channel "
                       "(derived: sum of the commenter's 'comments' weights on that channel's videos)",
    "has_topic": "topic weight supplied by the topic-modelling stage (in [0, 1]); no topics yet",
}

NODE_COLUMNS = {
    "node_id": "string", "node_type": "string", "key": "string", "label": "string",
    "channel_id": "string", "published_at": "datetime64[us, UTC]",
    "subscriber_count": "Int64", "view_count": "Int64", "video_count": "Int64",
    "like_count": "Int64", "comment_count": "Int64", "duration_seconds": "Int64",
}
EDGE_COLUMNS = {
    "source": "string", "target": "string", "relation": "string",
    "source_type": "string", "target_type": "string", "derived": "bool", "weight": "float64",
    "comment_count": "Int64", "reply_count": "Int64", "video_count": "Int64",
    "first_at": "datetime64[us, UTC]", "last_at": "datetime64[us, UTC]",
}
PSEUDONYM_RE = rf"^{HASH_PREFIX}[0-9a-f]{{64}}$"
_TYPE_ORDER = {t: i for i, t in enumerate(NODE_TYPES)}
_REL_ORDER = {r: i for i, r in enumerate(RELATIONS)}


class GraphBuildError(RuntimeError):
    """The input is not suitable for building the graph (e.g. not research-ready)."""


class GraphValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("graph validation failed:\n- " + "\n- ".join(errors))


@dataclass
class HeteroGraph:
    """Typed node and edge tables of one snapshot's research graph."""

    snapshot_id: str
    nodes: pd.DataFrame
    edges: pd.DataFrame
    manifest: dict[str, Any] = field(default_factory=dict)

    def nodes_of(self, node_type: str) -> pd.DataFrame:
        return self.nodes[self.nodes["node_type"] == node_type].reset_index(drop=True)

    def edges_of(self, relation: str) -> pd.DataFrame:
        return self.edges[self.edges["relation"] == relation].reset_index(drop=True)

    def fingerprint(self) -> str:
        """Content hash of the canonical tables (independent of file encoding)."""
        digest = hashlib.sha256()
        for df in (self.nodes, self.edges):
            digest.update(df.to_csv(index=False, date_format="%Y-%m-%dT%H:%M:%S.%fZ").encode("utf-8"))
        return digest.hexdigest()

    def to_networkx(self, *, include_derived: bool = True):
        """In-memory networkx.DiGraph with ``node_type`` / ``relation`` attributes.

        ``include_derived=False`` leaves out participates_in, so algorithms that walk
        commenter->video->channel do not count the same evidence twice.
        """
        import networkx as nx

        g = nx.DiGraph(snapshot_id=self.snapshot_id, graph_schema_version=GRAPH_SCHEMA_VERSION)
        for row in self.nodes.to_dict("records"):
            g.add_node(row["node_id"], **{k: _plain(v) for k, v in row.items() if k != "node_id" and not _isna(v)})
        edges = self.edges if include_derived else self.edges[~self.edges["derived"]]
        for row in edges.to_dict("records"):
            g.add_edge(row["source"], row["target"],
                       **{k: _plain(v) for k, v in row.items() if k not in ("source", "target") and not _isna(v)})
        return g


# --- construction ----------------------------------------------------------------------------

_NODE_SQL = {
    "channel": """
        SELECT 'channel:' || channel_id AS node_id, 'channel' AS node_type, channel_id AS key,
               channel_name AS label, channel_id, published_at, subscriber_count, view_count, video_count,
               NULL::BIGINT AS like_count, NULL::BIGINT AS comment_count, NULL::BIGINT AS duration_seconds
        FROM channels""",
    "video": """
        SELECT 'video:' || video_id, 'video', video_id, title, channel_id, published_at,
               NULL::BIGINT, view_count, NULL::BIGINT, like_count, comment_count, duration_seconds
        FROM videos""",
    "commenter": """
        SELECT DISTINCT 'commenter:' || author_channel_id, 'commenter', author_channel_id, NULL, NULL,
               NULL::TIMESTAMPTZ, NULL::BIGINT, NULL::BIGINT, NULL::BIGINT, NULL::BIGINT, NULL::BIGINT, NULL::BIGINT
        FROM comments WHERE author_channel_id IS NOT NULL""",
}

_EDGE_SQL = {
    # One weighted edge per (commenter, video); weight = number of comments.
    "comments": """
        SELECT 'commenter:' || author_channel_id AS source, 'video:' || video_id AS target,
               count(*)::DOUBLE AS weight, count(*) AS comment_count,
               count(*) FILTER (WHERE parent_comment_id IS NOT NULL) AS reply_count,
               NULL::BIGINT AS video_count, min(published_at) AS first_at, max(published_at) AS last_at
        FROM comments WHERE author_channel_id IS NOT NULL
        GROUP BY author_channel_id, video_id""",
    "belongs_to": """
        SELECT 'video:' || video_id, 'channel:' || channel_id, 1.0::DOUBLE,
               NULL::BIGINT, NULL::BIGINT, NULL::BIGINT, NULL::TIMESTAMPTZ, NULL::TIMESTAMPTZ
        FROM videos""",
    # Derived via the video's channel (videos table), never from comments.channel_id alone.
    "participates_in": """
        SELECT 'commenter:' || c.author_channel_id, 'channel:' || v.channel_id,
               count(*)::DOUBLE, count(*), count(*) FILTER (WHERE c.parent_comment_id IS NOT NULL),
               count(DISTINCT c.video_id), min(c.published_at), max(c.published_at)
        FROM comments c JOIN videos v USING (video_id)
        WHERE c.author_channel_id IS NOT NULL
        GROUP BY c.author_channel_id, v.channel_id""",
}


def build_graph(snapshot_id: str, *, topics: pd.DataFrame | None = None,
                video_topics: pd.DataFrame | None = None, require_research_ready: bool = True) -> HeteroGraph:
    """Build the heterogeneous graph of a research snapshot.

    ``topics`` (topic_id, label) and ``video_topics`` (video_id, topic_id, weight in [0, 1])
    are the hook for the later topic-modelling stage; without them the topic
    node / has_topic edge types are present but empty.
    """
    info = snapshots.get_research_snapshot(snapshot_id)
    if require_research_ready:
        report = rd.prepare(info.snapshot_id, export=False, save_report=False)
        if not report.research_ready:
            problems = [c.code for c in report.research_checks] or [f"quality {report.quality_status}"]
            raise GraphBuildError(f"snapshot {info.snapshot_id} is not research-ready: {problems}")

    with rd.research_session(info.snapshot_id) as con:
        node_frames = []
        for sql in _NODE_SQL.values():
            df = con.execute(sql).df()
            df.columns = list(NODE_COLUMNS)  # the SELECTs list columns in NODE_COLUMNS order
            node_frames.append(_typed(df, NODE_COLUMNS))
        nodes = pd.concat(node_frames, ignore_index=True)
        edge_frames = []
        for relation, sql in _EDGE_SQL.items():
            df = con.execute(sql).df()
            df.columns = ["source", "target", "weight", "comment_count", "reply_count", "video_count",
                          "first_at", "last_at"]
            src, dst, derived = RELATIONS[relation]
            df["relation"], df["source_type"], df["target_type"], df["derived"] = relation, src, dst, derived
            edge_frames.append(df)
        topic_nodes, topic_edges = _topic_tables(con, topics, video_topics)

    nodes = pd.concat([nodes, topic_nodes], ignore_index=True)
    edges = pd.concat([_typed(e, EDGE_COLUMNS) for e in edge_frames + [topic_edges]], ignore_index=True)
    graph = HeteroGraph(info.snapshot_id, _sort_nodes(nodes), _sort_edges(edges))
    graph.manifest = _manifest(graph, info)
    return graph


def _topic_tables(con, topics, video_topics) -> tuple[pd.DataFrame, pd.DataFrame]:
    if topics is None and video_topics is None:
        return _empty(NODE_COLUMNS), _empty(EDGE_COLUMNS)
    if topics is None or video_topics is None:
        raise GraphBuildError("topics and video_topics must be given together")
    con.register("t_topics", topics[["topic_id", "label"]])
    con.register("t_video_topics", video_topics[["video_id", "topic_id", "weight"]])
    tn = con.execute("""
        SELECT 'topic:' || topic_id AS node_id, 'topic' AS node_type, topic_id AS key, label,
               NULL AS channel_id, NULL::TIMESTAMPTZ AS published_at, NULL::BIGINT AS subscriber_count,
               NULL::BIGINT AS view_count, NULL::BIGINT AS video_count, NULL::BIGINT AS like_count,
               NULL::BIGINT AS comment_count, NULL::BIGINT AS duration_seconds
        FROM t_topics""").df()
    te = con.execute("""
        SELECT 'video:' || video_id AS source, 'topic:' || topic_id AS target, weight::DOUBLE AS weight,
               NULL::BIGINT AS comment_count, NULL::BIGINT AS reply_count, NULL::BIGINT AS video_count,
               NULL::TIMESTAMPTZ AS first_at, NULL::TIMESTAMPTZ AS last_at,
               'has_topic' AS relation, 'video' AS source_type, 'topic' AS target_type, false AS derived
        FROM t_video_topics""").df()
    return _typed(tn, NODE_COLUMNS), te


# --- validation ------------------------------------------------------------------------------

def validate_graph(graph: HeteroGraph) -> list[str]:
    """Graph-level checks; returns the list of problems (empty = valid). Never repairs."""
    n, e, errors = graph.nodes, graph.edges, []

    if n["node_id"].duplicated().any():
        errors.append(f"duplicate node ids: {sorted(n.loc[n['node_id'].duplicated(), 'node_id'])[:5]}")
    bad_types = sorted(set(n["node_type"]) - set(NODE_TYPES))
    if bad_types:
        errors.append(f"invalid node types: {bad_types}")
    prefix_ok = n.apply(lambda r: r["node_id"] == f"{r['node_type']}:{r['key']}", axis=1) if len(n) else pd.Series([], dtype=bool)
    if not prefix_ok.all():
        errors.append(f"{int((~prefix_ok).sum())} node id(s) not of the form <type>:<key>")
    commenters = n[n["node_type"] == "commenter"]["key"]
    raw = int((~commenters.str.fullmatch(PSEUDONYM_RE).fillna(False)).sum())
    if raw:
        errors.append(f"{raw} commenter node(s) are not pseudonyms (values not shown)")

    bad_rel = sorted(set(e["relation"]) - set(RELATIONS))
    if bad_rel:
        errors.append(f"invalid edge types: {bad_rel}")
    types = dict(zip(n["node_id"], n["node_type"]))
    for rel, (src_t, dst_t, derived) in RELATIONS.items():
        sub = e[e["relation"] == rel]
        missing = sub[~sub["source"].isin(types) | ~sub["target"].isin(types)]
        if len(missing):
            errors.append(f"{len(missing)} '{rel}' edge(s) reference missing nodes")
        wrong = sub[(sub["source"].map(types) != src_t) | (sub["target"].map(types) != dst_t)]
        if len(wrong) - len(missing) > 0:
            errors.append(f"{len(wrong) - len(missing)} '{rel}' edge(s) connect wrong node types")
        if len(sub) and (sub["derived"] != derived).any():
            errors.append(f"'{rel}' edges have the wrong 'derived' flag")
    if e.duplicated(["source", "target", "relation"]).any():
        errors.append(f"{int(e.duplicated(['source', 'target', 'relation']).sum())} duplicate edge(s)")
    if (e["source"] == e["target"]).any():
        errors.append(f"{int((e['source'] == e['target']).sum())} self-loop(s)")
    if e["weight"].isna().any() or (e["weight"] < 0).any():
        errors.append("edge weights must be non-negative numbers")
    topic_w = e.loc[e["relation"] == "has_topic", "weight"]
    if len(topic_w) and (topic_w > 1).any():
        errors.append("has_topic weights must be in [0, 1]")

    videos = set(n.loc[n["node_type"] == "video", "node_id"])
    belongs = e[e["relation"] == "belongs_to"]
    per_video = belongs.groupby("source").size()
    if set(per_video.index) != videos or (per_video != 1).any():
        errors.append("every video must belong to exactly one existing channel")

    # participates_in must equal the aggregation of comments edges through belongs_to.
    comments = e[e["relation"] == "comments"].merge(
        belongs[["source", "target"]].rename(columns={"source": "target", "target": "channel"}), on="target")
    expected = (comments.groupby(["source", "channel"])
                .agg(weight=("weight", "sum"), video_count=("target", "nunique"),
                     first_at=("first_at", "min"), last_at=("last_at", "max")).reset_index()
                .rename(columns={"channel": "target"}).sort_values(["source", "target"]).reset_index(drop=True))
    actual = (e[e["relation"] == "participates_in"][["source", "target", "weight", "video_count", "first_at", "last_at"]]
              .sort_values(["source", "target"]).reset_index(drop=True))
    if len(expected) != len(actual) or not (
            expected[["source", "target"]].astype(str).equals(actual[["source", "target"]].astype(str))
            and (expected["weight"].to_numpy() == actual["weight"].to_numpy()).all()
            and (expected["video_count"].astype("int64").to_numpy() == actual["video_count"].astype("int64").to_numpy()).all()
            and (expected["first_at"].to_numpy() == actual["first_at"].to_numpy()).all()
            and (expected["last_at"].to_numpy() == actual["last_at"].to_numpy()).all()):
        errors.append("participates_in edges are not derivable from comments + belongs_to")
    return errors


def ensure_valid(graph: HeteroGraph) -> HeteroGraph:
    errors = validate_graph(graph)
    if errors:
        raise GraphValidationError(errors)
    return graph


# --- statistics ---------------------------------------------------------------------------

def graph_statistics(graph: HeteroGraph, *, top_pairs: int = 20) -> dict[str, Any]:
    """Descriptive statistics (not Audience Bridge Scores)."""
    con = duckdb.connect()
    con.register("nodes", graph.nodes)
    con.register("edges", graph.edges)
    one = lambda sql: int(con.execute(sql).fetchone()[0])  # noqa: E731
    node_counts = {t: int((graph.nodes["node_type"] == t).sum()) for t in NODE_TYPES}
    edge_counts = {r: int((graph.edges["relation"] == r).sum()) for r in RELATIONS}
    pairs = con.execute(f"""
        SELECT a.target AS channel_a, b.target AS channel_b, count(*) AS shared_commenters
        FROM edges a JOIN edges b ON a.source = b.source AND a.target < b.target
        WHERE a.relation = 'participates_in' AND b.relation = 'participates_in'
        GROUP BY 1, 2 ORDER BY shared_commenters DESC, channel_a, channel_b LIMIT {int(top_pairs)}""").df()
    stats = {
        "node_counts": node_counts,
        "edge_counts": edge_counts,
        "total_nodes": int(len(graph.nodes)),
        "total_edges": int(len(graph.edges)),
        "total_edges_excluding_derived": int((~graph.edges["derived"]).sum()),
        "unique_commenters": node_counts["commenter"],
        "unique_videos": node_counts["video"],
        "unique_channels": node_counts["channel"],
        "commenters_on_multiple_channels": one("""
            SELECT count(*) FROM (SELECT source FROM edges WHERE relation = 'participates_in'
                                  GROUP BY source HAVING count(*) > 1)"""),
        "channel_pairs_with_shared_commenters": one("""
            SELECT count(*) FROM (SELECT DISTINCT a.target, b.target FROM edges a JOIN edges b
              ON a.source = b.source AND a.target < b.target
              WHERE a.relation = 'participates_in' AND b.relation = 'participates_in')"""),
        "top_channel_pairs": [{"channel_a": r.channel_a, "channel_b": r.channel_b,
                               "shared_commenters": int(r.shared_commenters)} for r in pairs.itertuples()],
        "note": "Descriptive graph statistics; shared commenters are interaction signals, not audience migration.",
    }
    con.close()
    return stats


# --- serialization -----------------------------------------------------------------------

def graph_dir(snapshot_id: str) -> Path:
    return component_dir(3) / snapshot_id / GRAPH_DIR


def save_graph(graph: HeteroGraph, directory: Path | None = None) -> Path:
    """Validate and write the graph once (nodes, edges, manifest). An identical
    existing graph is accepted; a different one is refused."""
    ensure_valid(graph)
    target = directory or graph_dir(graph.snapshot_id)
    if (target / MANIFEST_FILE).is_file():
        existing = json.loads((target / MANIFEST_FILE).read_text(encoding="utf-8"))
        if existing.get("fingerprint") == graph.fingerprint():
            return target
        raise FileExistsError(f"a different graph already exists at {target}")
    staging = target.with_name(f".{target.name}.staging")
    write_dataset(graph.nodes, staging / NODES_FILE, overwrite=True)
    write_dataset(graph.edges, staging / EDGES_FILE, overwrite=True)
    manifest = {**graph.manifest, "fingerprint": graph.fingerprint()}
    (staging / MANIFEST_FILE).write_text(json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")
    os.replace(staging, target)
    return target


def load_graph(directory: Path) -> HeteroGraph:
    """Reload a saved graph and check it is unchanged (fingerprint) and valid."""
    manifest = json.loads((directory / MANIFEST_FILE).read_text(encoding="utf-8"))
    graph = HeteroGraph(manifest["snapshot_id"], _sort_nodes(_typed(read_dataset(directory / NODES_FILE), NODE_COLUMNS)),
                        _sort_edges(_typed(read_dataset(directory / EDGES_FILE), EDGE_COLUMNS)), manifest)
    if graph.fingerprint() != manifest.get("fingerprint"):
        raise GraphValidationError(["graph files changed after they were saved (fingerprint mismatch)"])
    return ensure_valid(graph)


# --- helpers ----------------------------------------------------------------------------

def _manifest(graph: HeteroGraph, info) -> dict[str, Any]:
    return {
        "graph_schema_version": GRAPH_SCHEMA_VERSION,
        "snapshot_id": info.snapshot_id,
        "snapshot_created_at": info.manifest["created_at"],
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "node_types": list(NODE_TYPES),
        "relations": {r: {"source_type": s, "target_type": t, "derived": d} for r, (s, t, d) in RELATIONS.items()},
        "weight_definitions": WEIGHT_DEFINITIONS,
        "statistics": graph_statistics(graph),
    }


def _typed(df: pd.DataFrame, columns: dict[str, str]) -> pd.DataFrame:
    df = df.reindex(columns=list(columns))
    for col, dtype in columns.items():
        if dtype.startswith("datetime64"):
            df[col] = pd.to_datetime(df[col], utc=True).astype(dtype)
        else:
            df[col] = df[col].astype(dtype)
    return df


def _empty(columns: dict[str, str]) -> pd.DataFrame:
    return _typed(pd.DataFrame(columns=list(columns)), columns)


def _sort_nodes(nodes: pd.DataFrame) -> pd.DataFrame:
    order = nodes["node_type"].map(_TYPE_ORDER).fillna(len(_TYPE_ORDER))
    return nodes.assign(_o=order).sort_values(["_o", "node_id"], kind="stable").drop(columns="_o").reset_index(drop=True)


def _sort_edges(edges: pd.DataFrame) -> pd.DataFrame:
    order = edges["relation"].map(_REL_ORDER).fillna(len(_REL_ORDER))
    return (edges.assign(_o=order).sort_values(["_o", "source", "target"], kind="stable")
            .drop(columns="_o").reset_index(drop=True))


def _isna(v) -> bool:
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def _plain(v):
    return v.item() if hasattr(v, "item") else v


# --- command line ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="hetero_graph", description="Build the Component 3 heterogeneous graph.")
    parser.add_argument("--snapshot", help="research snapshot id (default: latest)")
    args = parser.parse_args(argv)
    try:
        sid = args.snapshot or snapshots.latest_research_snapshot().snapshot_id
        graph = build_graph(sid)
        path = save_graph(graph)
    except (GraphBuildError, GraphValidationError, FileExistsError, snapshots.SnapshotNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    s = graph.manifest["statistics"]
    print(f"Graph for snapshot {sid} (schema {GRAPH_SCHEMA_VERSION}) saved to {path}")
    print("  nodes: " + ", ".join(f"{k} {v}" for k, v in s["node_counts"].items()) + f" | total {s['total_nodes']}")
    print("  edges: " + ", ".join(f"{k} {v}" for k, v in s["edge_counts"].items()) + f" | total {s['total_edges']}")
    print(f"  commenters on 2+ channels {s['commenters_on_multiple_channels']} | channel pairs with shared "
          f"commenters {s['channel_pairs_with_shared_commenters']}")
    for p in s["top_channel_pairs"][:10]:
        print(f"    {p['channel_a']} <-> {p['channel_b']}: {p['shared_commenters']}")
    print(f"  fingerprint {graph.fingerprint()[:16]}...  (descriptive statistics only; no scores)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
