"""metapath2vec: primary heterogeneous representation learning for Component 3.

    python -m research.component_3.model.metapath2vec                      # latest snapshot, default config
    python -m research.component_3.model.metapath2vec --dim 64 --walks-per-node 10 --seed 7

1. Meta-path-guided random walks over the STEP 13 graph (explicit sampler below):
   every step must follow the meta-path's node-type and relation sequence.
2. Skip-gram with negative sampling on the walks (gensim Word2Vec, single worker,
   fixed seed, deterministic hashing -> reproducible across runs and processes).

Edges are walked in both directions (comments: commenter<->video, belongs_to:
video<->channel). The derived participates_in edges are never walked, so no
evidence is counted twice. Topic meta-paths become usable once topic nodes exist.

Output: data/processed/component_3/<snapshot_id>/embeddings/<experiment_id>/
  embeddings.parquet (node_id, node_type, snapshot_id, experiment_id, embedding)
  embeddings.npy     (float32 matrix in the same row order)
  experiment.json    (configuration, versions, walk statistics, coverage, validation)

Embeddings capture graph-structural relationships. They do NOT show audience
migration, causality, subscriber movement, influence or conversion. Nearest
neighbours are exploratory sanity checks, not scores or recommendations.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import zlib
from bisect import bisect_right
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from itertools import accumulate
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa

from research.component_3.preprocessing import hetero_graph as hg
from shared.utils import snapshots
from shared.utils.parquet_io import read_dataset, write_dataset

METHOD = "metapath2vec"
METHOD_VERSION = "1.0"
EMBEDDINGS_DIR = "embeddings"
WALKABLE_RELATIONS = ("comments", "belongs_to", "has_topic")  # participates_in is derived: not walked


@dataclass(frozen=True)
class MetaPath:
    """A cyclic node-type scheme, e.g. commenter -comments- video -comments- commenter."""

    name: str
    node_types: tuple[str, ...]
    relations: tuple[str, ...]
    purpose: str


# Default, documented meta-paths. Each is symmetric so walks can repeat it.
DEFAULT_METAPATHS = (
    MetaPath("CVC", ("commenter", "video", "commenter"), ("comments", "comments"),
             "commenters who comment on the same videos"),
    MetaPath("CVChVC", ("commenter", "video", "channel", "video", "commenter"),
             ("comments", "belongs_to", "belongs_to", "comments"),
             "commenter-to-channel structure (symmetric form of Commenter -> Video -> Channel)"),
    MetaPath("ChVCVCh", ("channel", "video", "commenter", "video", "channel"),
             ("belongs_to", "comments", "comments", "belongs_to"),
             "cross-channel connectivity through shared commenter participation"),
    MetaPath("VChV", ("video", "channel", "video"), ("belongs_to", "belongs_to"),
             "videos in the same channel context"),
)
# Available once topic nodes are populated (topic-modelling stage).
TOPIC_METAPATHS = (
    MetaPath("VTV", ("video", "topic", "video"), ("has_topic", "has_topic"), "videos sharing a topic"),
)


@dataclass(frozen=True)
class Config:
    metapaths: tuple[MetaPath, ...] = DEFAULT_METAPATHS
    walks_per_node: int = 10
    walk_length: int = 40            # nodes per walk
    transition_weights: str = "uniform"  # "uniform" | "log1p_comments" (STEP 14 interaction weight)
    dimensions: int = 64
    window: int = 5
    negative: int = 5
    epochs: int = 5
    learning_rate: float = 0.025
    min_learning_rate: float = 0.0001
    seed: int = 42

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["metapaths"] = [asdict(m) for m in self.metapaths]
        return d


class MetaPathError(ValueError):
    pass


class EmbeddingValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("embedding validation failed:\n- " + "\n- ".join(errors))


@dataclass
class EmbeddingResult:
    snapshot_id: str
    experiment_id: str
    nodes: pd.DataFrame          # node_id, node_type (row order of the matrix)
    vectors: np.ndarray          # float32 (n, dimensions)
    metadata: dict[str, Any] = field(default_factory=dict)

    def vector(self, node_id: str) -> np.ndarray:
        idx = self._index().get(node_id)
        if idx is None:
            raise KeyError(f"no embedding for {node_id}")
        return self.vectors[idx]

    def of_type(self, node_type: str) -> tuple[pd.DataFrame, np.ndarray]:
        mask = (self.nodes["node_type"] == node_type).to_numpy()
        return self.nodes[mask].reset_index(drop=True), self.vectors[mask]

    def _index(self) -> dict[str, int]:
        return {n: i for i, n in enumerate(self.nodes["node_id"])}


# --- meta-path validation ----------------------------------------------------------------

def validate_metapath(mp: MetaPath, graph: hg.HeteroGraph) -> list[str]:
    """Problems that make a meta-path unusable on this graph (empty list = usable)."""
    problems = []
    t, r = mp.node_types, mp.relations
    if len(t) < 2 or len(r) != len(t) - 1:
        return [f"{mp.name}: needs n node types and n-1 relations"]
    if t[0] != t[-1]:
        problems.append(f"{mp.name}: must start and end with the same node type to be repeated "
                        f"(use a symmetric form, e.g. commenter-video-channel-video-commenter)")
    for nt in t:
        if nt not in hg.NODE_TYPES:
            problems.append(f"{mp.name}: invalid node type '{nt}'")
    for i, rel in enumerate(r):
        if rel not in hg.RELATIONS:
            problems.append(f"{mp.name}: invalid relation '{rel}'")
            continue
        if rel not in WALKABLE_RELATIONS:
            problems.append(f"{mp.name}: relation '{rel}' is derived and not walked (avoids double counting)")
            continue
        src, dst, _ = hg.RELATIONS[rel]
        if {t[i], t[i + 1]} != {src, dst}:
            problems.append(f"{mp.name}: '{rel}' cannot connect {t[i]} -> {t[i + 1]} "
                            f"(it links {src} and {dst})")
    if problems:
        return problems
    counts = graph.edges["relation"].value_counts()
    for nt in set(t):
        if not (graph.nodes["node_type"] == nt).any():
            problems.append(f"{mp.name}: no '{nt}' nodes in the graph"
                            + (" (topic modelling has not run yet)" if nt == "topic" else ""))
    for rel in set(r):
        if counts.get(rel, 0) == 0:
            problems.append(f"{mp.name}: no '{rel}' edges in the graph")
    return problems


def usable_metapaths(config: Config, graph: hg.HeteroGraph) -> tuple[list[MetaPath], dict[str, list[str]]]:
    usable, skipped = [], {}
    for mp in config.metapaths:
        problems = validate_metapath(mp, graph)
        if problems:
            skipped[mp.name] = problems
        else:
            usable.append(mp)
    return usable, skipped


# --- heterogeneous walks -------------------------------------------------------------------

class _Adjacency:
    """Sorted neighbour lists per (node, relation, neighbour type), both edge directions."""

    def __init__(self, graph: hg.HeteroGraph, transition_weights: str):
        if transition_weights not in ("uniform", "log1p_comments"):
            raise ValueError("transition_weights must be 'uniform' or 'log1p_comments'")
        types = dict(zip(graph.nodes["node_id"], graph.nodes["node_type"]))
        self.types = types
        nbrs: dict[tuple[str, str, str], list[tuple[str, float]]] = {}
        walkable = graph.edges[graph.edges["relation"].isin(WALKABLE_RELATIONS)]
        for src, dst, rel, w in zip(walkable["source"], walkable["target"], walkable["relation"], walkable["weight"]):
            weight = float(np.log1p(w)) if (transition_weights == "log1p_comments" and rel == "comments") else 1.0
            nbrs.setdefault((src, rel, types[dst]), []).append((dst, weight))
            nbrs.setdefault((dst, rel, types[src]), []).append((src, weight))
        self.neighbours = {k: sorted(v) for k, v in nbrs.items()}
        self.cumulative = {k: list(accumulate(w for _, w in v)) for k, v in self.neighbours.items()}

    def step(self, node: str, relation: str, next_type: str, rng: np.random.Generator) -> str | None:
        key = (node, relation, next_type)
        options = self.neighbours.get(key)
        if not options:
            return None
        cum = self.cumulative[key]
        return options[bisect_right(cum, rng.random() * cum[-1])][0] if len(options) > 1 else options[0][0]


def generate_walks(graph: hg.HeteroGraph, config: Config) -> tuple[list[list[str]], dict[str, Any]]:
    """Meta-path-guided walks; deterministic for a given graph, config and seed."""
    rng = np.random.default_rng(config.seed)
    adj = _Adjacency(graph, config.transition_weights)
    metapaths, skipped = usable_metapaths(config, graph)
    if not metapaths:
        raise MetaPathError("no usable meta-path: " + json.dumps(skipped))
    walks: list[list[str]] = []
    stats: dict[str, Any] = {"per_metapath": {}, "skipped_metapaths": skipped}
    for mp in metapaths:
        starts = sorted(graph.nodes.loc[graph.nodes["node_type"] == mp.node_types[0], "node_id"])
        cycle = len(mp.relations)
        made = truncated = 0
        for _ in range(config.walks_per_node):
            for start in starts:
                walk = [start]
                while len(walk) < config.walk_length:
                    i = (len(walk) - 1) % cycle
                    nxt = adj.step(walk[-1], mp.relations[i], mp.node_types[i + 1], rng)
                    if nxt is None:
                        truncated += 1
                        break
                    walk.append(nxt)
                if len(walk) > 1:
                    walks.append(walk)
                    made += 1
        stats["per_metapath"][mp.name] = {"start_nodes": len(starts), "walks": made, "truncated": truncated}
    stats["total_walks"] = len(walks)
    stats["mean_walk_length"] = float(np.mean([len(w) for w in walks])) if walks else 0.0
    return walks, stats


def walk_respects_metapath(walk: list[str], mp: MetaPath, types: dict[str, str]) -> bool:
    cycle = len(mp.relations)
    return all(types[n] == mp.node_types[i % cycle] for i, n in enumerate(walk))


# --- training ----------------------------------------------------------------------------

def _stable_hash(token: str) -> int:
    return zlib.crc32(token.encode("utf-8"))  # deterministic across processes (unlike hash())


def train(graph: hg.HeteroGraph, config: Config = Config()) -> EmbeddingResult:
    """Sample meta-path walks and train skip-gram embeddings (reproducible for a fixed seed)."""
    from gensim.models import Word2Vec
    import gensim

    walks, walk_stats = generate_walks(graph, config)
    losses: list[float] = []
    model = Word2Vec(vector_size=config.dimensions, window=config.window, min_count=1, sg=1, hs=0,
                     negative=config.negative, alpha=config.learning_rate, min_alpha=config.min_learning_rate,
                     seed=config.seed, workers=1, hashfxn=_stable_hash, compute_loss=True)
    model.build_vocab(walks)
    model.train(walks, total_examples=len(walks), epochs=config.epochs, compute_loss=True)
    losses.append(float(model.get_latest_training_loss()))

    types = dict(zip(graph.nodes["node_id"], graph.nodes["node_type"]))
    order = sorted(model.wv.index_to_key, key=lambda n: (hg.NODE_TYPES.index(types[n]), n))
    vectors = np.vstack([model.wv[n] for n in order]).astype(np.float32) if order else \
        np.zeros((0, config.dimensions), np.float32)
    nodes = pd.DataFrame({"node_id": order, "node_type": [types[n] for n in order]}).astype("string")

    experiment_id = make_experiment_id(graph, config)
    result = EmbeddingResult(graph.snapshot_id, experiment_id, nodes, vectors)
    result.metadata = {
        "method": METHOD, "method_version": METHOD_VERSION,
        "experiment_id": experiment_id, "snapshot_id": graph.snapshot_id,
        "graph_fingerprint": graph.fingerprint(),
        "config": config.to_dict(),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "versions": {"python": platform.python_version(), "numpy": np.__version__, "gensim": gensim.__version__,
                     "pandas": pd.__version__},
        "training": {"skip_gram": True, "negative_sampling": True, "workers": 1,
                     "hash": "crc32 (deterministic)", "final_training_loss": losses[-1]},
        "walks": walk_stats,
        "coverage": coverage(graph, result),
        "note": "Embedding similarity captures graph structure only; it does not show audience migration, "
                "causality, subscriber movement, influence or conversion.",
    }
    result.metadata["validation"] = validate_embeddings(result, graph, config)
    return result


def make_experiment_id(graph: hg.HeteroGraph, config: Config) -> str:
    """Deterministic id: same snapshot graph + configuration -> same experiment id."""
    payload = json.dumps({"graph": graph.fingerprint(), "config": config.to_dict(), "method": METHOD_VERSION},
                         sort_keys=True)
    return f"m2v-{hashlib.sha256(payload.encode()).hexdigest()[:12]}"


# --- coverage / validation / sanity checks ---------------------------------------------------

def coverage(graph: hg.HeteroGraph, result: EmbeddingResult) -> dict[str, Any]:
    embedded = set(result.nodes["node_id"])
    per_type = {}
    for t in hg.NODE_TYPES:
        ids = set(graph.nodes.loc[graph.nodes["node_type"] == t, "node_id"])
        per_type[t] = {"graph_nodes": len(ids), "embedded": len(ids & embedded), "missing": len(ids - embedded)}
    total = len(graph.nodes)
    return {"total_graph_nodes": total, "nodes_with_embeddings": len(embedded),
            "nodes_without_embeddings": total - len(embedded & set(graph.nodes["node_id"])),
            "coverage_ratio": (len(embedded) / total) if total else None, "per_type": per_type,
            "why_missing": "a node gets no embedding only if no usable meta-path walk visits it "
                           "(e.g. a channel without stored videos, or topic nodes before topic modelling)"}


def validate_embeddings(result: EmbeddingResult, graph: hg.HeteroGraph, config: Config,
                        *, min_coverage: float = 0.0) -> dict[str, Any]:
    errors = []
    if result.vectors.shape != (len(result.nodes), config.dimensions):
        errors.append(f"matrix shape {result.vectors.shape} != ({len(result.nodes)}, {config.dimensions})")
    if not np.isfinite(result.vectors).all():
        errors.append("embeddings contain NaN or infinite values")
    types = dict(zip(graph.nodes["node_id"], graph.nodes["node_type"]))
    unknown = [n for n in result.nodes["node_id"] if n not in types]
    if unknown:
        errors.append(f"{len(unknown)} embedded node(s) are not in the graph")
    wrong = [n for n, t in zip(result.nodes["node_id"], result.nodes["node_type"]) if types.get(n, t) != t]
    if wrong:
        errors.append(f"{len(wrong)} node(s) with a node type different from the graph")
    if result.nodes["node_id"].duplicated().any():
        errors.append("duplicate node ids")
    commenters = result.nodes.loc[result.nodes["node_type"] == "commenter", "node_id"].str.removeprefix("commenter:")
    if (~commenters.str.fullmatch(hg.PSEUDONYM_RE).fillna(False)).any():
        errors.append("commenter ids that are not pseudonyms (values not shown)")
    cov = len(result.nodes) / len(graph.nodes) if len(graph.nodes) else 0.0
    if cov < min_coverage:
        errors.append(f"coverage {cov:.3f} below the required {min_coverage:.3f}")
    if errors:
        raise EmbeddingValidationError(errors)
    return {"passed": True, "dimensions": config.dimensions, "finite": True, "coverage_ratio": cov}


def nearest_neighbours(result: EmbeddingResult, node_id: str, k: int = 5, *,
                       same_type: bool = True) -> pd.DataFrame:
    """Cosine nearest neighbours (sanity check; not an evaluation or a score)."""
    v = result.vector(node_id)
    node_type = result.nodes.loc[result.nodes["node_id"] == node_id, "node_type"].iloc[0]
    nodes, mat = (result.of_type(node_type) if same_type else (result.nodes, result.vectors))
    norms = np.linalg.norm(mat, axis=1) * np.linalg.norm(v)
    sims = np.divide(mat @ v, norms, out=np.zeros(len(mat)), where=norms > 0)
    df = nodes.assign(cosine_similarity=sims)
    df = df[df["node_id"] != node_id].sort_values(["cosine_similarity", "node_id"], ascending=[False, True])
    return df.head(k).reset_index(drop=True)


def channel_similarity_exploratory(result: EmbeddingResult, channel_node_id: str, k: int = 5) -> pd.DataFrame:
    """Embedding similarity — exploratory. NOT an Audience Bridge Score and NOT a recommendation."""
    df = nearest_neighbours(result, channel_node_id, k, same_type=True)
    return df.assign(label="Embedding similarity — exploratory")


# --- persistence ----------------------------------------------------------------------------

def embeddings_dir(snapshot_id: str, experiment_id: str) -> Path:
    return hg.graph_dir(snapshot_id).parent / EMBEDDINGS_DIR / experiment_id


def save_embeddings(result: EmbeddingResult, directory: Path | None = None, *,
                    extra_files: dict[str, Any] | None = None) -> Path:
    """Write once. Re-saving the same experiment is accepted if the vectors match (tolerance 1e-6).

    Shared by all Component 3 embedding methods (``model_type`` column from the
    metadata's ``method``). ``extra_files`` maps a file name to a function that
    writes it (e.g. a model checkpoint); they are written in the same atomic step.
    """
    target = directory or embeddings_dir(result.snapshot_id, result.experiment_id)
    if (target / "experiment.json").is_file():
        existing = load_embeddings(target)
        same = (existing.nodes["node_id"].tolist() == result.nodes["node_id"].tolist()
                and np.allclose(existing.vectors, result.vectors, atol=1e-6))
        if same:
            return target
        raise FileExistsError(f"experiment {result.experiment_id} already exists with different embeddings")
    staging = target.with_name(f".{target.name}.staging")
    table = result.nodes.assign(
        snapshot_id=result.snapshot_id, experiment_id=result.experiment_id,
        model_type=result.metadata.get("method", METHOD),
        embedding=pd.Series([v.astype(np.float64).tolist() for v in result.vectors],
                            dtype=pd.ArrowDtype(pa.list_(pa.float64()))))
    write_dataset(table, staging / "embeddings.parquet", overwrite=True)
    np.save(staging / "embeddings.npy", result.vectors)
    for name, writer in (extra_files or {}).items():
        writer(staging / name)
    meta = {**result.metadata, "row_order": "embeddings.npy rows follow embeddings.parquet rows",
            "vectors_sha256": hashlib.sha256(result.vectors.tobytes()).hexdigest()}
    (staging / "experiment.json").write_text(json.dumps(meta, indent=2, default=str) + "\n", encoding="utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging, target)
    return target


def load_embeddings(directory: Path) -> EmbeddingResult:
    meta = json.loads((directory / "experiment.json").read_text(encoding="utf-8"))
    table = read_dataset(directory / "embeddings.parquet")
    vectors = np.load(directory / "embeddings.npy")
    if hashlib.sha256(vectors.tobytes()).hexdigest() != meta.get("vectors_sha256"):
        raise EmbeddingValidationError(["embeddings.npy changed after saving (checksum mismatch)"])
    from_table = np.array([list(v) for v in table["embedding"]], dtype=np.float32) if len(table) else vectors
    if from_table.shape != vectors.shape or not np.allclose(from_table, vectors, atol=1e-6):
        raise EmbeddingValidationError(["embeddings.parquet and embeddings.npy disagree"])
    nodes = table[["node_id", "node_type"]].astype("string").reset_index(drop=True)  # model_type kept in metadata
    return EmbeddingResult(meta["snapshot_id"], meta["experiment_id"], nodes, vectors, meta)


# --- command line ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="metapath2vec", description="Train metapath2vec embeddings (Component 3).")
    p.add_argument("--snapshot", help="research snapshot id (default: latest)")
    p.add_argument("--dim", type=int, default=Config.dimensions)
    p.add_argument("--walks-per-node", type=int, default=Config.walks_per_node)
    p.add_argument("--walk-length", type=int, default=Config.walk_length)
    p.add_argument("--window", type=int, default=Config.window)
    p.add_argument("--negative", type=int, default=Config.negative)
    p.add_argument("--epochs", type=int, default=Config.epochs)
    p.add_argument("--weights", choices=["uniform", "log1p_comments"], default=Config.transition_weights)
    p.add_argument("--seed", type=int, default=Config.seed)
    args = p.parse_args(argv)
    try:
        sid = args.snapshot or snapshots.latest_research_snapshot().snapshot_id
        path = hg.graph_dir(sid)
        graph = hg.load_graph(path) if (path / hg.MANIFEST_FILE).is_file() else hg.build_graph(sid)
        config = Config(walks_per_node=args.walks_per_node, walk_length=args.walk_length,
                        transition_weights=args.weights, dimensions=args.dim, window=args.window,
                        negative=args.negative, epochs=args.epochs, seed=args.seed)
        result = train(graph, config)
        out = save_embeddings(result)
    except (MetaPathError, EmbeddingValidationError, FileExistsError, hg.GraphBuildError,
            snapshots.SnapshotNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    m = result.metadata
    print(f"metapath2vec {result.experiment_id} on {sid} saved to {out}")
    for name, st in m["walks"]["per_metapath"].items():
        print(f"  {name}: {st['walks']} walks from {st['start_nodes']} start nodes ({st['truncated']} truncated)")
    for name, why in m["walks"]["skipped_metapaths"].items():
        print(f"  {name}: skipped - {'; '.join(why)}")
    c = m["coverage"]
    print(f"  embeddings: {c['nodes_with_embeddings']}/{c['total_graph_nodes']} nodes "
          + ", ".join(f"{t} {v['embedded']}/{v['graph_nodes']}" for t, v in c["per_type"].items()))
    channels, _ = result.of_type("channel")
    if len(channels):
        first = channels["node_id"].iloc[0]
        print(f"  Embedding similarity — exploratory (not a score), nearest channels to {first}:")
        for r in channel_similarity_exploratory(result, first, 3).itertuples():
            print(f"    {r.node_id}: cosine {r.cosine_similarity:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
