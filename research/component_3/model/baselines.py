"""Component 3 BASELINE methods: Louvain communities and node2vec channel similarity.

    python -m research.component_3.model.baselines louvain
    python -m research.component_3.model.baselines node2vec --dim 64 --p 1 --q 1

These are comparison baselines, NOT the proposed method (heterogeneous graph ->
metapath2vec / HGT -> Personalized PageRank -> topic similarity -> confidence ->
Audience Bridge Score). They reuse the same research snapshot, STEP 13 graph and
STEP 14 features, so STEP 21 can compare them fairly.

* Louvain: community detection on a channel-channel projection of shared commenter
  participation (edge weight = STEP 14 channel-pair Jaccard by default).
  Community membership = structural community association only.
* node2vec: homogeneous (type-agnostic) biased random walks (p, q) over the same
  observed STEP 13 edges as metapath2vec + skip-gram; channel-to-channel cosine
  similarity = structural graph proximity only.

Neither shows audience migration, audience transfer, causality, future growth or
business outcomes.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.component_3.model import metapath2vec as m2v
from research.component_3.preprocessing import graph_features as gf
from research.component_3.preprocessing import hetero_graph as hg
from shared.utils import snapshots
from shared.utils.parquet_io import read_dataset, write_dataset

BASELINES_DIR = "baselines"
PROJECTION_WEIGHTS = {
    "jaccard": "STEP 14 jaccard_similarity = |A ∩ B| / |A ∪ B| of the two channels' commenter sets "
               "(size-normalized, in [0, 1])",
    "shared_commenters": "STEP 14 shared_commenter_count = |A ∩ B| (raw; favours large channels)",
    "log1p_shared": "ln(1 + shared_commenter_count) (dampens large counts)",
}


class BaselineError(ValueError):
    pass


# --- shared baseline input ---------------------------------------------------------------------

@dataclass(frozen=True)
class BaselineInput:
    """What both baselines see: one snapshot's graph and channel-pair features (as of the snapshot)."""

    snapshot_id: str
    graph: hg.HeteroGraph
    channels: list[str]            # channel node ids, sorted
    pair_features: pd.DataFrame    # STEP 14 channel_pair_features (observed pairs)
    as_of: datetime


def load_input(snapshot_id: str) -> BaselineInput:
    info = snapshots.get_research_snapshot(snapshot_id)
    gpath = hg.graph_dir(info.snapshot_id)
    graph = hg.load_graph(gpath) if (gpath / hg.MANIFEST_FILE).is_file() else hg.build_graph(info.snapshot_id)
    as_of = gf._snapshot_time(info)
    fpath = gf.features_dir(info.snapshot_id, as_of)
    fs = gf.load_features(fpath) if (fpath / gf.MANIFEST_FILE).is_file() else \
        gf.build_features(info.snapshot_id, as_of=as_of, graph=graph)
    channels = sorted(graph.nodes.loc[graph.nodes["node_type"] == "channel", "node_id"])
    return BaselineInput(info.snapshot_id, graph, channels, fs["channel_pair_features"], as_of)


def channel_projection(inp: BaselineInput, weight: str = "jaccard") -> pd.DataFrame:
    """Undirected channel-channel edges from shared commenter participation (observed pairs only).

    Source: STEP 14 channel_pair_features (derived from commenter -> video -> channel). Every
    channel stays a node even without edges. Columns: channel_a, channel_b, shared_commenters, weight.
    """
    if weight not in PROJECTION_WEIGHTS:
        raise BaselineError(f"projection weight must be one of {sorted(PROJECTION_WEIGHTS)}")
    p = inp.pair_features
    if p.duplicated(["channel_a", "channel_b"]).any():
        raise BaselineError("duplicate channel pairs in the projection input")
    if not (p["channel_a"].isin(inp.channels) & p["channel_b"].isin(inp.channels)).all():
        raise BaselineError("projection references channels that are not in the graph")
    shared = p["shared_commenter_count"].astype(float)
    w = {"jaccard": p["jaccard_similarity"].astype(float), "shared_commenters": shared,
         "log1p_shared": np.log1p(shared)}[weight]
    edges = pd.DataFrame({"channel_a": p["channel_a"].astype(str), "channel_b": p["channel_b"].astype(str),
                          "shared_commenters": p["shared_commenter_count"].astype("int64"), "weight": w.to_numpy()})
    edges = edges[edges["weight"] > 0]
    if not np.isfinite(edges["weight"]).all():
        raise BaselineError("non-finite projection weights")
    return edges.sort_values(["channel_a", "channel_b"]).reset_index(drop=True)


def _experiment_id(prefix: str, inp: BaselineInput, config: dict[str, Any]) -> str:
    payload = json.dumps({"graph": inp.graph.fingerprint(), "snapshot": inp.snapshot_id, "config": config},
                         sort_keys=True, default=str)
    return f"{prefix}-{hashlib.sha256(payload.encode()).hexdigest()[:12]}"


def _common_metadata(method: str, experiment_id: str, inp: BaselineInput, config: dict[str, Any],
                     projection: str, edge_weight: str) -> dict[str, Any]:
    return {
        "method": method, "role": "baseline (not the proposed method)", "experiment_id": experiment_id,
        "snapshot_id": inp.snapshot_id, "graph_fingerprint": inp.graph.fingerprint(),
        "as_of": inp.as_of.isoformat().replace("+00:00", "Z"),
        "channel_set": inp.channels, "graph_projection": projection, "edge_weight_definition": edge_weight,
        "seed": config.get("seed"), "parameters": config,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "versions": {"python": platform.python_version(), "numpy": np.__version__},
    }


def baseline_dir(snapshot_id: str, experiment_id: str) -> Path:
    return hg.graph_dir(snapshot_id).parent / BASELINES_DIR / experiment_id


# --- Louvain -------------------------------------------------------------------------------------

@dataclass(frozen=True)
class LouvainConfig:
    projection_weight: str = "jaccard"
    resolution: float = 1.0
    threshold: float = 1e-7
    seed: int = 42

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LouvainResult:
    snapshot_id: str
    experiment_id: str
    communities: pd.DataFrame
    relationships: pd.DataFrame
    metadata: dict[str, Any] = field(default_factory=dict)


def run_louvain(inp: BaselineInput, config: LouvainConfig = LouvainConfig()) -> LouvainResult:
    import networkx as nx

    if not config.resolution > 0:
        raise BaselineError("resolution must be > 0")
    if not inp.channels:
        raise BaselineError("the graph has no channels")
    edges = channel_projection(inp, config.projection_weight)
    g = nx.Graph()
    g.add_nodes_from(inp.channels)  # sorted insertion order -> deterministic with the seed
    g.add_weighted_edges_from(edges[["channel_a", "channel_b", "weight"]].itertuples(index=False))
    parts = nx.community.louvain_communities(g, weight="weight", resolution=config.resolution,
                                             threshold=config.threshold, seed=config.seed)
    # stable community ids: by size (desc), then smallest member id
    parts = sorted((sorted(c) for c in parts), key=lambda c: (-len(c), c[0]))
    membership = {ch: (f"c{i:02d}", len(c)) for i, c in enumerate(parts) for ch in c}
    degree = dict(g.degree())
    modularity = float(nx.community.modularity(g, [set(c) for c in parts], weight="weight",
                                               resolution=config.resolution)) if g.number_of_edges() else None

    experiment_id = _experiment_id("louvain", inp, config.to_dict())
    common = {"snapshot_id": inp.snapshot_id, "experiment_id": experiment_id}
    communities = pd.DataFrame([{"channel_id": ch, "community_id": membership[ch][0],
                                 "community_size": membership[ch][1], "is_isolated": degree[ch] == 0, **common}
                                for ch in inp.channels]).astype({"community_size": "int64"})
    pair_shared = {(a, b): s for a, b, s in zip(edges["channel_a"], edges["channel_b"], edges["shared_commenters"])}
    pair_w = {(a, b): w for a, b, w in zip(edges["channel_a"], edges["channel_b"], edges["weight"])}
    rows = []
    for a in inp.channels:
        for b in inp.channels:
            if a == b:
                continue
            key = (min(a, b), max(a, b))
            same = membership[a][0] == membership[b][0]
            rows.append({"source_channel_id": a, "destination_channel_id": b, "same_community": same,
                         # documented binary indicator; NOT a graded similarity score
                         "community_relationship": 1.0 if same else 0.0,
                         "shared_commenters": int(pair_shared.get(key, 0)),
                         "projection_weight": float(pair_w.get(key, 0.0)), **common})
    rel = pd.DataFrame(rows, columns=["source_channel_id", "destination_channel_id", "same_community",
                                      "community_relationship", "shared_commenters", "projection_weight",
                                      "snapshot_id", "experiment_id"])
    result = LouvainResult(inp.snapshot_id, experiment_id, communities, rel)
    result.metadata = {
        **_common_metadata("louvain", experiment_id, inp, config.to_dict(),
                           "channel-channel projection of shared commenter participation (STEP 14 channel pairs)",
                           PROJECTION_WEIGHTS[config.projection_weight]),
        "library": f"networkx {nx.__version__} louvain_communities",
        "communities": len(parts), "modularity": modularity,
        "isolated_channels": int(sum(1 for ch in inp.channels if degree[ch] == 0)),
        "projection_edges": int(len(edges)),
        "community_relationship": "1.0 if both channels are in the same community, else 0.0 (binary)",
        "note": "Community membership is structural community association only; it does not show audience "
                "migration, audience transfer, causality or future growth.",
    }
    _validate_louvain(result, inp)
    return result


def _validate_louvain(r: LouvainResult, inp: BaselineInput) -> None:
    errors = []
    c = r.communities
    if c["channel_id"].duplicated().any() or set(c["channel_id"]) != set(inp.channels):
        errors.append("each graph channel must appear exactly once")
    sizes = c.groupby("community_id")["channel_id"].count()
    if not (c["community_size"] == c["community_id"].map(sizes)).all():
        errors.append("community_size does not match membership")
    rel = r.relationships
    if (rel["source_channel_id"] == rel["destination_channel_id"]).any():
        errors.append("self pairs in relationships")
    if errors:
        raise BaselineError("Louvain validation failed: " + "; ".join(errors))


def save_louvain(r: LouvainResult) -> Path:
    files = {"louvain_communities.parquet": r.communities, "louvain_channel_relationships.parquet": r.relationships}
    return _save(baseline_dir(r.snapshot_id, r.experiment_id), files, r.metadata)


# --- node2vec --------------------------------------------------------------------------------

@dataclass(frozen=True)
class Node2VecConfig:
    dimensions: int = 64
    walk_length: int = 40
    walks_per_node: int = 10
    window: int = 5
    p: float = 1.0          # return parameter
    q: float = 1.0          # in-out parameter
    negative: int = 5
    epochs: int = 5
    weighted: bool = True   # comments edges weighted ln(1 + comment_count) (STEP 14), belongs_to 1.0
    seed: int = 42

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Node2VecResult:
    snapshot_id: str
    experiment_id: str
    embeddings: m2v.EmbeddingResult
    similarity: pd.DataFrame
    metadata: dict[str, Any] = field(default_factory=dict)


def homogeneous_adjacency(graph: hg.HeteroGraph, weighted: bool) -> dict[str, list[tuple[str, float]]]:
    """Type-agnostic undirected view of the observed STEP 13 edges (comments, belongs_to).
    participates_in (derived) is excluded, as for metapath2vec. Node types are ignored."""
    e = graph.edges[graph.edges["relation"].isin(["comments", "belongs_to"])]
    adj: dict[str, dict[str, float]] = {}
    for s, t, rel, w in zip(e["source"], e["target"], e["relation"], e["weight"]):
        weight = float(np.log1p(w)) if (weighted and rel == "comments") else 1.0
        for a, b in ((s, t), (t, s)):
            adj.setdefault(a, {})
            adj[a][b] = adj[a].get(b, 0.0) + weight  # duplicate edges are merged (summed)
    return {n: sorted(nb.items()) for n, nb in sorted(adj.items())}


def node2vec_walks(adj: dict[str, list[tuple[str, float]]], config: Node2VecConfig) -> list[list[str]]:
    """Second-order biased walks (Grover & Leskovec): unnormalized weight w * (1/p back to the
    previous node, 1 to a neighbour of the previous node, 1/q further away). Seeded and ordered."""
    rng = np.random.default_rng(config.seed)
    neigh_sets = {n: {x for x, _ in nb} for n, nb in adj.items()}
    walks = []
    for _ in range(config.walks_per_node):
        for start in adj:  # sorted
            walk = [start]
            while len(walk) < config.walk_length:
                cur = walk[-1]
                nbrs = adj.get(cur, [])
                if not nbrs:
                    break
                if len(walk) == 1:
                    probs = np.array([w for _, w in nbrs])
                else:
                    prev = walk[-2]
                    probs = np.array([w / config.p if x == prev else w if x in neigh_sets[prev] else w / config.q
                                      for x, w in nbrs])
                walk.append(nbrs[int(rng.choice(len(nbrs), p=probs / probs.sum()))][0])
            if len(walk) > 1:
                walks.append(walk)
    return walks


def run_node2vec(inp: BaselineInput, config: Node2VecConfig = Node2VecConfig()) -> Node2VecResult:
    from gensim.models import Word2Vec
    import gensim

    for name in ("dimensions", "walk_length", "walks_per_node", "window", "negative", "epochs"):
        if getattr(config, name) < 1:
            raise BaselineError(f"{name} must be >= 1")
    if config.walk_length < 2 or not config.p > 0 or not config.q > 0:
        raise BaselineError("walk_length must be >= 2 and p, q must be > 0")
    if not inp.channels:
        raise BaselineError("the graph has no channels")
    adj = homogeneous_adjacency(inp.graph, config.weighted)
    walks = node2vec_walks(adj, config)
    experiment_id = _experiment_id("node2vec", inp, config.to_dict())
    types = dict(zip(inp.graph.nodes["node_id"], inp.graph.nodes["node_type"]))

    if walks:
        model = Word2Vec(vector_size=config.dimensions, window=config.window, min_count=1, sg=1, hs=0,
                         negative=config.negative, seed=config.seed, workers=1, hashfxn=m2v._stable_hash)
        model.build_vocab(walks)
        model.train(walks, total_examples=len(walks), epochs=config.epochs)
        order = sorted(model.wv.index_to_key, key=lambda n: (hg.NODE_TYPES.index(types[n]), n))
        vectors = np.vstack([model.wv[n] for n in order]).astype(np.float32)
    else:
        order, vectors = [], np.zeros((0, config.dimensions), np.float32)
    nodes = pd.DataFrame({"node_id": order, "node_type": [types[n] for n in order]}).astype("string")
    emb = m2v.EmbeddingResult(inp.snapshot_id, experiment_id, nodes, vectors)

    similarity = channel_similarity(emb, inp.channels)
    similarity = similarity.assign(snapshot_id=inp.snapshot_id, experiment_id=experiment_id)
    result = Node2VecResult(inp.snapshot_id, experiment_id, emb, similarity)
    result.metadata = {
        **_common_metadata("node2vec", experiment_id, inp, config.to_dict(),
                           "homogeneous (type-agnostic) undirected view of the observed STEP 13 edges "
                           "(comments, belongs_to); participates_in excluded",
                           "comments: ln(1 + comment_count) (STEP 14 interaction_weight) if weighted else 1.0; "
                           "belongs_to: 1.0"),
        "library": f"gensim {gensim.__version__} Word2Vec (skip-gram, negative sampling, 1 worker, crc32 hash)",
        "walks": {"total": len(walks), "nodes_in_graph_view": len(adj)},
        "coverage": m2v.coverage(inp.graph, emb),
        "similarity": "raw_node2vec_similarity = cosine(channel embeddings), range [-1, 1], symmetric; "
                      "normalized_node2vec_similarity = (raw + 1) / 2, a linear order-preserving map to [0, 1] "
                      "(no clipping); rank per source by raw (ties: destination_channel_id)",
        "note": "node2vec similarity is structural graph proximity only; it does not show audience movement, "
                "audience transfer, growth or business outcomes.",
    }
    result.metadata["method"] = "node2vec"
    emb.metadata = result.metadata
    _validate_node2vec(result, inp, config)
    return result


def channel_similarity(emb: m2v.EmbeddingResult, channels: list[str]) -> pd.DataFrame:
    """Ordered channel pairs (no self pairs); cosine of channel embeddings. Channels without an
    embedding (never visited by a walk) get NULL similarity and no rank."""
    index = {n: i for i, n in enumerate(emb.nodes["node_id"])}
    rows = []
    for a in channels:
        for b in channels:
            if a == b:
                continue
            raw = None
            if a in index and b in index:
                va, vb = emb.vectors[index[a]].astype(float), emb.vectors[index[b]].astype(float)
                na, nb = np.linalg.norm(va), np.linalg.norm(vb)
                raw = float(va @ vb / (na * nb)) if na > 0 and nb > 0 else None
            rows.append({"source_channel_id": a, "destination_channel_id": b, "raw_node2vec_similarity": raw})
    df = pd.DataFrame(rows, columns=["source_channel_id", "destination_channel_id", "raw_node2vec_similarity"])
    df["raw_node2vec_similarity"] = df["raw_node2vec_similarity"].astype("float64")
    df["normalized_node2vec_similarity"] = (df["raw_node2vec_similarity"] + 1.0) / 2.0
    df = df.sort_values(["source_channel_id", "raw_node2vec_similarity", "destination_channel_id"],
                        ascending=[True, False, True], na_position="last", kind="stable").reset_index(drop=True)
    df["rank"] = df.groupby("source_channel_id")["raw_node2vec_similarity"].rank(method="first", ascending=False)
    df["rank"] = df["rank"].astype("Int64")
    return df


def _validate_node2vec(r: Node2VecResult, inp: BaselineInput, config: Node2VecConfig) -> None:
    errors = []
    v = r.embeddings.vectors
    if v.shape[1:] != (config.dimensions,) or not np.isfinite(v).all():
        errors.append("embeddings must be finite with the configured dimension")
    s = r.similarity
    if (s["source_channel_id"] == s["destination_channel_id"]).any():
        errors.append("self pairs in similarity")
    vals = s["raw_node2vec_similarity"].dropna()
    if not np.isfinite(vals).all() or ((vals < -1 - 1e-6) | (vals > 1 + 1e-6)).any():
        errors.append("raw similarity must be finite and within [-1, 1]")
    commenters = r.embeddings.nodes.loc[r.embeddings.nodes["node_type"] == "commenter", "node_id"]
    if (~commenters.str.removeprefix("commenter:").str.fullmatch(hg.PSEUDONYM_RE).fillna(False)).any():
        errors.append("commenter ids that are not pseudonyms (values not shown)")
    if errors:
        raise BaselineError("node2vec validation failed: " + "; ".join(errors))


def save_node2vec(r: Node2VecResult) -> Path:
    target = baseline_dir(r.snapshot_id, r.experiment_id)
    return m2v.save_embeddings(r.embeddings, target, extra_files={
        "node2vec_channel_similarity.parquet": lambda path: write_dataset(r.similarity, path, overwrite=True)})


def load_node2vec(directory: Path) -> Node2VecResult:
    emb = m2v.load_embeddings(directory)
    sim = read_dataset(directory / "node2vec_channel_similarity.parquet")
    return Node2VecResult(emb.snapshot_id, emb.experiment_id, emb, sim, emb.metadata)


# --- persistence helper -----------------------------------------------------------------------

def _save(target: Path, tables: dict[str, pd.DataFrame], metadata: dict[str, Any]) -> Path:
    if (target / "baseline_run.json").is_file():
        same = all((target / n).is_file() and read_dataset(target / n).reset_index(drop=True)
                   .equals(df.reset_index(drop=True)) for n, df in tables.items())
        if same:
            return target
        raise FileExistsError(f"baseline experiment already exists with different outputs: {target}")
    staging = target.with_name(f".{target.name}.staging")
    for name, df in tables.items():
        write_dataset(df, staging / name, overwrite=True)
    (staging / "baseline_run.json").write_text(json.dumps(metadata, indent=2, default=str) + "\n", encoding="utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging, target)
    return target


# --- command line ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="baselines", description="Component 3 baselines (Louvain, node2vec).")
    ap.add_argument("method", choices=["louvain", "node2vec"])
    ap.add_argument("--snapshot", help="research snapshot id (default: latest)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--resolution", type=float, default=LouvainConfig.resolution)
    ap.add_argument("--projection-weight", choices=sorted(PROJECTION_WEIGHTS), default=LouvainConfig.projection_weight)
    ap.add_argument("--dim", type=int, default=Node2VecConfig.dimensions)
    ap.add_argument("--p", type=float, default=Node2VecConfig.p)
    ap.add_argument("--q", type=float, default=Node2VecConfig.q)
    ap.add_argument("--walks-per-node", type=int, default=Node2VecConfig.walks_per_node)
    ap.add_argument("--walk-length", type=int, default=Node2VecConfig.walk_length)
    args = ap.parse_args(argv)
    try:
        inp = load_input(args.snapshot or snapshots.latest_research_snapshot().snapshot_id)
        if args.method == "louvain":
            r = run_louvain(inp, LouvainConfig(projection_weight=args.projection_weight,
                                               resolution=args.resolution, seed=args.seed))
            out = save_louvain(r)
            m = r.metadata
            print(f"Louvain baseline {r.experiment_id} on {inp.snapshot_id} -> {out}")
            print(f"  communities {m['communities']} | modularity {m['modularity']} | isolated channels "
                  f"{m['isolated_channels']} | projection edges {m['projection_edges']}")
            print("  (structural community association only; baseline, not the proposed method)")
        else:
            r = run_node2vec(inp, Node2VecConfig(dimensions=args.dim, p=args.p, q=args.q, seed=args.seed,
                                                 walks_per_node=args.walks_per_node, walk_length=args.walk_length))
            out = save_node2vec(r)
            s = r.similarity.dropna(subset=["raw_node2vec_similarity"])
            print(f"node2vec baseline {r.experiment_id} on {inp.snapshot_id} -> {out}")
            print(f"  embeddings {len(r.embeddings.nodes)} | channel pairs {len(r.similarity)} | raw similarity "
                  f"{s.raw_node2vec_similarity.min():.3f} .. {s.raw_node2vec_similarity.max():.3f}")
            print("  (structural graph proximity only; baseline, not the proposed method)")
    except (BaselineError, FileExistsError, snapshots.SnapshotNotFoundError, hg.GraphBuildError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
