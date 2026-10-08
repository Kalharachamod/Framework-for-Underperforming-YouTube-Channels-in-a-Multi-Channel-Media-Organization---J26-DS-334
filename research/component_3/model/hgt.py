"""HGT (Heterogeneous Graph Transformer): ALTERNATIVE graph learning for Component 3.

    python -m research.component_3.model.hgt                     # latest snapshot, default config
    python -m research.component_3.model.hgt --hidden 64 --layers 2 --heads 2 --epochs 50 --seed 7

metapath2vec (STEP 15) remains the PRIMARY method; HGT is an alternative for an
empirical comparison on the same snapshot graph and node universe.

Input: the STEP 13 graph (same nodes / relations as metapath2vec), STEP 14
public-metric features. Model: type-specific input projections -> L x HGTConv
(PyTorch Geometric) -> node embeddings. Objective: self-supervised link
prediction on the observed behavioural relation commenter-comments-video, with
type-respecting negative sampling. Split: temporal when it yields enough
"warm" validation edges, otherwise a documented random-edge fallback.

Leakage control: message passing and commenter / degree features use TRAINING
edges only; public metrics come from STEP 14 as of the training boundary.

Output (shared format with metapath2vec, model_type = HGT):
  data/processed/component_3/<snapshot_id>/embeddings/<hgt-...>/
  embeddings.parquet, embeddings.npy, experiment.json, model.pt

Embeddings capture learned graph structure; they do NOT show audience migration,
causality, subscriber movement, conversion or influence.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from research.component_3.model import metapath2vec as m2v
from research.component_3.preprocessing import graph_features as gf
from research.component_3.preprocessing import hetero_graph as hg
from shared.utils import snapshots

METHOD = "HGT"
METHOD_VERSION = "1.0"
TARGET_RELATION = ("commenter", "comments", "video")
STRUCTURAL_RELATIONS = ("belongs_to", "has_topic")   # always used for message passing (not predicted)

# Public, non-interaction node features from STEP 14 (log1p for counts; years for ages).
PUBLIC_FEATURES = {
    "channel": [("observed_subscriber_count", "log1p"), ("observed_view_count", "log1p"),
                ("observed_api_video_count", "log1p"), ("age_days", "years")],
    "video": [("observed_view_count", "log1p"), ("observed_like_count", "log1p"),
              ("observed_api_comment_count", "log1p"), ("age_days", "years")],
    "commenter": [],   # every commenter attribute is derived from comments -> training edges only
    "topic": [],
}


@dataclass(frozen=True)
class HGTConfig:
    hidden: int = 64
    layers: int = 2
    heads: int = 2
    dropout: float = 0.2
    learning_rate: float = 0.005
    weight_decay: float = 1e-4
    epochs: int = 50
    negatives_per_positive: int = 5
    validation_fraction: float = 0.2      # newest share of edges (temporal) / random share (fallback)
    min_validation_edges: int = 20        # warm validation edges needed for a temporal split
    positive_weighting: str = "none"      # "none" | "log1p_comments"
    seed: int = 42

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HGTError(ValueError):
    pass


@dataclass
class Split:
    kind: str                      # "temporal" | "random_edge_split_fallback"
    train: pd.DataFrame            # comments edges used for training (message passing + positives)
    valid: pd.DataFrame            # held-out positive comments edges
    boundary: datetime             # features / evidence are "as of" this time
    reason: str
    details: dict[str, Any] = field(default_factory=dict)


# --- split ------------------------------------------------------------------------------------

def make_split(graph: hg.HeteroGraph, config: HGTConfig, snapshot_time: datetime) -> Split:
    """Temporal split by the edge's first comment time; fall back to a seeded random edge split."""
    edges = graph.edges_of("comments").sort_values(["first_at", "source", "target"], kind="stable")
    if len(edges) < 2:
        raise HGTError("the graph has fewer than 2 comment edges; nothing to learn")
    cutoff = edges["first_at"].quantile(1 - config.validation_fraction)
    train = edges[edges["first_at"] <= cutoff]
    later = edges[edges["first_at"] > cutoff]
    warm = later[later["source"].isin(train["source"]) & later["target"].isin(train["target"])]
    details = {"cutoff": cutoff.isoformat(), "post_cutoff_edges": int(len(later)), "warm_post_cutoff_edges": int(len(warm))}
    if len(warm) >= config.min_validation_edges:
        return Split("temporal", train.reset_index(drop=True), warm.reset_index(drop=True),
                     cutoff.to_pydatetime(),
                     "validation = edges first observed after the cutoff whose commenter and video "
                     "already appear in training", details)
    rng = np.random.default_rng(config.seed)
    order = rng.permutation(len(edges))
    n_val = max(1, int(round(len(edges) * config.validation_fraction)))
    valid, train = edges.iloc[order[:n_val]], edges.iloc[order[n_val:]]
    valid = valid[valid["source"].isin(train["source"]) & valid["target"].isin(train["target"])]
    if valid.empty:
        raise HGTError("not enough edges for a validation split")
    return Split("random_edge_split_fallback", train.sort_values(["source", "target"]).reset_index(drop=True),
                 valid.sort_values(["source", "target"]).reset_index(drop=True), snapshot_time,
                 f"not a temporal evaluation: only {len(warm)} post-cutoff edge(s) involve a commenter and video "
                 f"seen before the cutoff (need {config.min_validation_edges}); most later edges are cold-start",
                 details)


# --- graph -> HeteroData ----------------------------------------------------------------------

def to_hetero_data(graph: hg.HeteroGraph, comments_edges: pd.DataFrame, public: pd.DataFrame | None,
                   *, stats: dict[str, Any] | None = None):
    """STEP 13 graph -> torch_geometric HeteroData (sparse edge_index per relation, both directions).

    ``comments_edges`` are the commenter-video edges allowed for message passing and
    degree features (training edges during training). ``stats`` = feature
    standardization fitted on the training graph (computed here if None).
    Returns (data, index, stats) where index[type] = ordered node ids.
    """
    import torch
    from torch_geometric.data import HeteroData

    data = HeteroData()
    present = [t for t in hg.NODE_TYPES if (graph.nodes["node_type"] == t).any()]
    index = {t: sorted(graph.nodes.loc[graph.nodes["node_type"] == t, "node_id"]) for t in present}
    pos = {t: {n: i for i, n in enumerate(ids)} for t, ids in index.items()}

    rel_edges = {"comments": comments_edges}
    for rel in STRUCTURAL_RELATIONS:
        rel_edges[rel] = graph.edges_of(rel)
    for rel, e in rel_edges.items():
        src_t, dst_t, _ = hg.RELATIONS[rel]
        if src_t not in pos or dst_t not in pos or e.empty:
            continue
        s = torch.tensor([pos[src_t][x] for x in e["source"]], dtype=torch.long)
        d = torch.tensor([pos[dst_t][x] for x in e["target"]], dtype=torch.long)
        data[src_t, rel, dst_t].edge_index = torch.stack([s, d])
        data[dst_t, f"rev_{rel}", src_t].edge_index = torch.stack([d, s])
        if rel == "comments":
            data[src_t, rel, dst_t].edge_weight = torch.tensor(e["weight"].to_numpy(), dtype=torch.float32)

    raw = _raw_features(graph, index, comments_edges, public)
    if stats is None:
        stats = {t: {"mean": f.mean(0).tolist(), "std": f.std(0).tolist()} for t, f in raw.items()}
    for t, f in raw.items():
        mean, std = np.array(stats[t]["mean"]), np.array(stats[t]["std"])
        z = np.where(std > 0, (f - mean) / np.where(std > 0, std, 1), 0.0)
        data[t].x = torch.tensor(z, dtype=torch.float32)
        data[t].num_nodes = len(index[t])
    return data, index, stats


def _raw_features(graph, index, comments_edges, public) -> dict[str, np.ndarray]:
    """Type-specific feature matrices. Missing values -> 0 plus an explicit missing-indicator column."""
    deg_c = comments_edges.groupby("source").agg(videos=("target", "nunique"), weight=("weight", "sum"))
    belongs = graph.edges_of("belongs_to")
    video_channel = dict(zip(belongs["source"], belongs["target"]))
    ch_per_commenter = (comments_edges.assign(ch=comments_edges["target"].map(video_channel))
                        .groupby("source")["ch"].nunique())
    deg_v = comments_edges.groupby("target")["source"].nunique()
    videos_per_channel = belongs.groupby("target")["source"].nunique()
    pub = public.set_index("node_id") if public is not None and len(public) else pd.DataFrame()

    out = {}
    for t, ids in index.items():
        cols: list[np.ndarray] = []
        for name, transform in PUBLIC_FEATURES.get(t, []):
            vals = pd.to_numeric(pub[name].reindex(ids), errors="coerce").astype("float64") if name in pub else \
                pd.Series(np.nan, index=ids)
            missing = vals.isna().to_numpy()
            v = vals.fillna(0).to_numpy()
            v = np.log1p(np.clip(v, 0, None)) if transform == "log1p" else v / 365.25
            cols += [v, missing.astype(float)]
        if t == "commenter":
            cols += [np.log1p(deg_c["videos"].reindex(ids).fillna(0).to_numpy()),
                     np.log1p(deg_c["weight"].reindex(ids).fillna(0).to_numpy()),
                     np.log1p(ch_per_commenter.reindex(ids).fillna(0).to_numpy())]
        elif t == "video":
            cols.append(np.log1p(deg_v.reindex(ids).fillna(0).to_numpy()))
        elif t == "channel":
            cols.append(np.log1p(videos_per_channel.reindex(ids).fillna(0).to_numpy()))
        else:
            cols.append(np.ones(len(ids)))  # topic: no features fabricated; a constant input only
        out[t] = np.column_stack(cols).astype(np.float64)
    return out


# --- model ---------------------------------------------------------------------------------

def build_model(metadata, in_dims: dict[str, int], config: HGTConfig):
    import torch
    from torch import nn
    from torch_geometric.nn import HGTConv

    class HGT(nn.Module):
        def __init__(self):
            super().__init__()
            self.proj = nn.ModuleDict({t: nn.Linear(d, config.hidden) for t, d in in_dims.items()})
            self.convs = nn.ModuleList([HGTConv(config.hidden, config.hidden, metadata, heads=config.heads)
                                        for _ in range(config.layers)])
            self.dropout = nn.Dropout(config.dropout)

        def forward(self, x_dict, edge_index_dict):
            h = {t: torch.relu(self.proj[t](x)) for t, x in x_dict.items()}
            for i, conv in enumerate(self.convs):
                out = conv(h, edge_index_dict)
                h = {t: (out.get(t) if out.get(t) is not None else h[t]) for t in h}  # keep isolated types
                if i < len(self.convs) - 1:
                    h = {t: self.dropout(torch.relu(v)) for t, v in h.items()}
            return h

    return HGT()


def sample_negatives(pos_src: np.ndarray, n_targets: int, known: set[tuple[int, int]], k: int,
                     rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """k negatives per positive: same commenter, a random VIDEO (target type preserved) that the
    commenter is not known to comment on. Deterministic for a given rng state."""
    src = np.repeat(pos_src, k)
    dst = rng.integers(0, n_targets, size=len(src))
    for _ in range(20):  # resample collisions with known positives
        bad = np.array([(s, d) in known for s, d in zip(src, dst)], dtype=bool)
        if not bad.any():
            break
        dst[bad] = rng.integers(0, n_targets, size=int(bad.sum()))
    keep = np.array([(s, d) not in known for s, d in zip(src, dst)], dtype=bool)
    return src[keep], dst[keep]


# --- training ------------------------------------------------------------------------------

def train(graph: hg.HeteroGraph, config: HGTConfig = HGTConfig(), *,
          features_for=None) -> tuple[m2v.EmbeddingResult, Any]:
    """Train HGT with link prediction; returns (embeddings for every graph node, trained model)."""
    import torch
    import torch.nn.functional as F
    import torch_geometric

    info = snapshots.get_research_snapshot(graph.snapshot_id)
    snapshot_time = gf._snapshot_time(info)
    features_for = features_for or (lambda as_of: gf.build_features(graph.snapshot_id, as_of=as_of, graph=graph))
    split = make_split(graph, config, snapshot_time)
    train_public = features_for(split.boundary)["graph_node_features"]

    torch.manual_seed(config.seed)
    torch.use_deterministic_algorithms(True, warn_only=True)
    threads = torch.get_num_threads()
    torch.set_num_threads(1)
    try:
        data, index, stats = to_hetero_data(graph, split.train, train_public)
        pos = {t: {n: i for i, n in enumerate(ids)} for t, ids in index.items()}
        s_t, rel, d_t = TARGET_RELATION
        ci, vi = pos[s_t], pos[d_t]
        all_comments = graph.edges_of("comments")
        known = {(ci[a], vi[b]) for a, b in zip(all_comments["source"], all_comments["target"])}
        tr_src = np.array([ci[x] for x in split.train["source"]])
        tr_dst = np.array([vi[x] for x in split.train["target"]])
        tr_w = (np.log1p(split.train["weight"].to_numpy()) if config.positive_weighting == "log1p_comments"
                else np.ones(len(tr_src)))
        va_src = np.array([ci[x] for x in split.valid["source"]])
        va_dst = np.array([vi[x] for x in split.valid["target"]])
        rng = np.random.default_rng(config.seed)
        vn_src, vn_dst = sample_negatives(va_src, len(vi), known, config.negatives_per_positive, rng)

        model = build_model(data.metadata(), {t: data[t].x.shape[1] for t in data.node_types}, config)
        opt = torch.optim.Adam(model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay)
        history = []
        started = time.perf_counter()
        for epoch in range(1, config.epochs + 1):
            model.train()
            ns, nd = sample_negatives(tr_src, len(vi), known, config.negatives_per_positive, rng)
            h = model(data.x_dict, data.edge_index_dict)
            pos_logit = (h[s_t][tr_src] * h[d_t][tr_dst]).sum(-1)
            neg_logit = (h[s_t][ns] * h[d_t][nd]).sum(-1)
            loss = (F.binary_cross_entropy_with_logits(pos_logit, torch.ones_like(pos_logit),
                                                       weight=torch.tensor(tr_w, dtype=torch.float32))
                    + F.binary_cross_entropy_with_logits(neg_logit, torch.zeros_like(neg_logit)))
            opt.zero_grad()
            loss.backward()
            opt.step()
            model.eval()
            with torch.no_grad():
                h = model(data.x_dict, data.edge_index_dict)
                vp = (h[s_t][va_src] * h[d_t][va_dst]).sum(-1)
                vn = (h[s_t][vn_src] * h[d_t][vn_dst]).sum(-1)
                vloss = (F.binary_cross_entropy_with_logits(vp, torch.ones_like(vp))
                         + F.binary_cross_entropy_with_logits(vn, torch.zeros_like(vn))).item()
                scores = np.concatenate([vp.numpy(), vn.numpy()])
                labels = np.concatenate([np.ones(len(vp)), np.zeros(len(vn))])
            history.append({"epoch": epoch, "train_loss": float(loss.item()), "valid_loss": float(vloss),
                            "valid_roc_auc": roc_auc(labels, scores), "valid_average_precision": average_precision(labels, scores)})
        duration = time.perf_counter() - started

        # Final embeddings: full snapshot evidence (all comment edges, features as of the snapshot),
        # standardized with the TRAINING statistics.
        full_public = features_for(snapshot_time)["graph_node_features"]
        full, full_index, _ = to_hetero_data(graph, all_comments, full_public, stats=stats)
        model.eval()
        with torch.no_grad():
            h = model(full.x_dict, full.edge_index_dict)
    finally:
        torch.set_num_threads(threads)

    order = [(n, t) for t in hg.NODE_TYPES if t in full_index for n in full_index[t]]
    vectors = np.vstack([h[t].numpy() for t in hg.NODE_TYPES if t in full_index]).astype(np.float32)
    nodes = pd.DataFrame(order, columns=["node_id", "node_type"]).astype("string")
    experiment_id = make_experiment_id(graph, config)
    result = m2v.EmbeddingResult(graph.snapshot_id, experiment_id, nodes, vectors)
    result.metadata = {
        "method": METHOD, "method_version": METHOD_VERSION, "role": "alternative (metapath2vec is primary)",
        "experiment_id": experiment_id, "snapshot_id": graph.snapshot_id, "graph_fingerprint": graph.fingerprint(),
        "config": config.to_dict(),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "versions": {"python": platform.python_version(), "torch": torch.__version__,
                     "torch_geometric": torch_geometric.__version__, "numpy": np.__version__},
        "objective": "link prediction on commenter-comments-video; dot-product decoder; binary cross-entropy "
                     "on observed edges vs type-preserving negative videos",
        "negative_sampling": {"per_positive": config.negatives_per_positive, "corrupted_side": "video",
                              "excludes_known_positives": True, "seeded": True},
        "split": {"kind": split.kind, "reason": split.reason, "boundary": split.boundary.isoformat(),
                  "train_edges": int(len(split.train)), "validation_edges": int(len(split.valid)), **split.details},
        "message_passing": {"training": "training comment edges + belongs_to (+ reverse edges)",
                            "inference": "all snapshot comment edges + belongs_to (+ reverse edges)",
                            "participates_in": "not used (derived; would leak held-out edges)"},
        "node_features": {t: [f for f, _ in PUBLIC_FEATURES[t]] + ({"commenter": ["videos", "comment_weight",
                          "channels"], "video": ["commenters"], "channel": ["stored_videos"]}.get(t, ["constant"]))
                          for t in full_index},
        "edge_features": "HGTConv has no edge attributes: relation type is modelled by relation-specific "
                         "attention; comment weights only optionally weight the positive loss",
        "feature_standardization": "per type, fitted on the training graph only",
        "training": {"history": history, "final": history[-1] if history else None,
                     "duration_seconds": round(duration, 3), "threads": 1},
        "coverage": m2v.coverage(graph, result),
        "note": "HGT is an alternative to metapath2vec (primary). Embedding similarity captures learned graph "
                "structure only; it does not show audience migration, causality, subscriber movement, "
                "conversion or influence.",
    }
    result.metadata["validation"] = m2v.validate_embeddings(
        result, graph, m2v.Config(dimensions=config.hidden))
    return result, model


def make_experiment_id(graph: hg.HeteroGraph, config: HGTConfig) -> str:
    payload = json.dumps({"graph": graph.fingerprint(), "config": config.to_dict(), "method": METHOD_VERSION},
                         sort_keys=True)
    return f"hgt-{hashlib.sha256(payload.encode()).hexdigest()[:12]}"


def save(result: m2v.EmbeddingResult, model) -> Any:
    """Shared embedding format + model checkpoint (state dict) in the same experiment directory."""
    import torch

    return m2v.save_embeddings(result, extra_files={
        "model.pt": lambda path: torch.save({"state_dict": model.state_dict(),
                                             "config": result.metadata["config"],
                                             "experiment_id": result.experiment_id,
                                             "snapshot_id": result.snapshot_id}, path)})


def hgt_similarity_exploratory(result: m2v.EmbeddingResult, channel_node_id: str, k: int = 5) -> pd.DataFrame:
    """HGT embedding similarity — exploratory. NOT an Audience Bridge Score or a recommendation."""
    return m2v.nearest_neighbours(result, channel_node_id, k).assign(label="HGT embedding similarity — exploratory")


# --- metrics (no extra dependency) -----------------------------------------------------------

def roc_auc(labels: np.ndarray, scores: np.ndarray) -> float | None:
    pos, neg = scores[labels == 1], scores[labels == 0]
    if not len(pos) or not len(neg):
        return None
    ranks = pd.Series(scores).rank(method="average").to_numpy()
    return float((ranks[labels == 1].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def average_precision(labels: np.ndarray, scores: np.ndarray) -> float | None:
    if not labels.sum():
        return None
    order = np.argsort(-scores, kind="stable")
    hits = labels[order]
    precision = np.cumsum(hits) / np.arange(1, len(hits) + 1)
    return float((precision * hits).sum() / hits.sum())


# --- command line ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="hgt", description="Train HGT embeddings (Component 3 alternative).")
    p.add_argument("--snapshot", help="research snapshot id (default: latest)")
    d = HGTConfig()
    p.add_argument("--hidden", type=int, default=d.hidden)
    p.add_argument("--layers", type=int, default=d.layers)
    p.add_argument("--heads", type=int, default=d.heads)
    p.add_argument("--epochs", type=int, default=d.epochs)
    p.add_argument("--lr", type=float, default=d.learning_rate)
    p.add_argument("--seed", type=int, default=d.seed)
    args = p.parse_args(argv)
    try:
        sid = args.snapshot or snapshots.latest_research_snapshot().snapshot_id
        path = hg.graph_dir(sid)
        graph = hg.load_graph(path) if (path / hg.MANIFEST_FILE).is_file() else hg.build_graph(sid)
        cfg = HGTConfig(hidden=args.hidden, layers=args.layers, heads=args.heads, epochs=args.epochs,
                        learning_rate=args.lr, seed=args.seed)
        result, model = train(graph, cfg)
        out = save(result, model)
    except (HGTError, m2v.EmbeddingValidationError, FileExistsError, hg.GraphBuildError,
            snapshots.SnapshotNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    md = result.metadata
    sp, fin = md["split"], md["training"]["final"]
    print(f"HGT {result.experiment_id} on {sid} saved to {out}")
    print(f"  split: {sp['kind']} - {sp['reason']}")
    print(f"  edges: train {sp['train_edges']}, validation {sp['validation_edges']}")
    print(f"  final epoch {fin['epoch']}: train loss {fin['train_loss']:.4f}, valid loss {fin['valid_loss']:.4f}, "
          f"ROC-AUC {fin['valid_roc_auc']}, AP {fin['valid_average_precision']}")
    c = md["coverage"]
    print(f"  embeddings: {c['nodes_with_embeddings']}/{c['total_graph_nodes']} nodes")
    channels, _ = result.of_type("channel")
    if len(channels):
        first = channels["node_id"].iloc[0]
        print(f"  HGT embedding similarity — exploratory (not a score), nearest channels to {first}:")
        for r in hgt_similarity_exploratory(result, first, 3).itertuples():
            print(f"    {r.node_id}: cosine {r.cosine_similarity:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
