"""Personalized PageRank diffusion over the Component 3 heterogeneous graph.

    python -m research.component_3.model.ppr_diffusion                       # all eligible source channels
    python -m research.component_3.model.ppr_diffusion --alpha 0.85 --source UC...

For each source channel: personalization on the source -> PPR over the
commenter-video-channel graph -> channel-node scores -> ranked destination
channels (``diffusion_score``). This is a graph diffusion / structural
connectivity signal (a potential audience bridge signal). It is NOT an
Audience Bridge Score and does not show audience migration, causality,
subscriber movement, conversion or guaranteed growth.

Design (explicit, not library defaults):
  * graph: observed STEP 13 edges, relation-aware BIDIRECTIONAL
      commenter <-comments-> video <-belongs_to-> channel  (+ has_topic later)
    reverse edges are labelled ``derived_diffusion_edge``; participates_in is
    excluded by default (derived from comments + belongs_to: no double counting)
  * weights: comments = ln(1 + comment_count) (STEP 14 interaction_weight),
    belongs_to = 1.0, times an optional per-relation/direction multiplier
  * transitions: P(i->j) = w(i,j) / sum_k w(i,k)   ("weight_proportional", default)
    or "relation_balanced": equal share per (relation, direction) group, then w/sum within the group
  * PPR: r = (1 - alpha) p + alpha (P^T r + d p), d = mass on dangling nodes
    (dangling mass returns to the personalization = the source); sparse power
    iteration until ||r_t - r_{t-1}||_1 < tol or max_iter (convergence recorded)

Output: data/processed/component_3/<snapshot_id>/diffusion/<ppr-...>/
  channel_diffusion.parquet, diffusion_run.json
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
import scipy
from scipy import sparse

from research.component_3.preprocessing import hetero_graph as hg
from shared.utils import snapshots
from shared.utils.parquet_io import read_dataset, write_dataset

METHOD = "personalized_pagerank"
METHOD_VERSION = "1.0"
EDGE_WEIGHTING_VERSION = "step14-interaction_weight-ln1p-v1"
DIFFUSION_DIR = "diffusion"
RESULT_COLUMNS = {
    "source_channel_id": "string", "destination_channel_id": "string", "diffusion_score": "float64",
    "normalized_destination_share": "float64", "rank": "Int64", "reachable": "bool", "is_source": "bool",
    "snapshot_id": "string", "experiment_id": "string",
}


@dataclass(frozen=True)
class PPRConfig:
    alpha: float = 0.85                    # damping: probability of following an edge
    tolerance: float = 1e-10               # L1 change between iterations
    max_iterations: int = 1000
    directionality: str = "relation_aware_bidirectional"   # the only supported mode (documented)
    transition_rule: str = "weight_proportional"            # or "relation_balanced"
    include_derived_participation: bool = False             # participates_in shortcut edges
    relation_weights: tuple[tuple[str, float], ...] = ()    # e.g. (("comments:reverse", 0.5),)
    personalization: str = "source_channel"                 # or "source_channel_videos"
    include_source: bool = False                            # source excluded from destination ranking
    include_topic_edges: bool = False                       # has_topic edges; off: topic enters the score separately

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["relation_weights"] = dict(self.relation_weights)
        return d


class DiffusionError(ValueError):
    pass


@dataclass
class DiffusionGraph:
    """Sparse row-stochastic transition matrix over all graph nodes (fixed, sorted order)."""

    node_ids: list[str]
    node_types: np.ndarray
    transition: sparse.csr_matrix
    edges: pd.DataFrame            # diffusion edges: source, target, relation, direction, kind, weight
    dangling: np.ndarray           # bool per node: no outgoing transitions

    @property
    def index(self) -> dict[str, int]:
        return {n: i for i, n in enumerate(self.node_ids)}


@dataclass
class DiffusionRun:
    snapshot_id: str
    experiment_id: str
    results: pd.DataFrame
    metadata: dict[str, Any] = field(default_factory=dict)


# --- diffusion graph ---------------------------------------------------------------------

def build_diffusion_graph(graph: hg.HeteroGraph, config: PPRConfig = PPRConfig()) -> DiffusionGraph:
    if config.directionality != "relation_aware_bidirectional":
        raise DiffusionError("directionality must be 'relation_aware_bidirectional' (see documentation)")
    if config.transition_rule not in ("weight_proportional", "relation_balanced"):
        raise DiffusionError("transition_rule must be 'weight_proportional' or 'relation_balanced'")
    multipliers = dict(config.relation_weights)
    for key, value in multipliers.items():
        rel, _, direction = key.partition(":")
        if rel not in hg.RELATIONS or direction not in ("forward", "reverse") or not value >= 0:
            raise DiffusionError(f"invalid relation weight {key!r}={value!r}")

    nodes = graph.nodes.sort_values("node_id", kind="stable")
    node_ids = nodes["node_id"].tolist()
    index = {n: i for i, n in enumerate(node_ids)}
    # has_topic is excluded by default so diffusion stays an audience-structure signal: topic content
    # enters the Audience Bridge Score through its own topic-similarity component (no double counting).
    relations = ["comments", "belongs_to"] + (["has_topic"] if config.include_topic_edges else [])         + (["participates_in"] if config.include_derived_participation else [])
    observed = graph.edges[graph.edges["relation"].isin(relations)]

    base = np.where(observed["relation"].isin(["comments", "participates_in"]),
                    np.log1p(observed["weight"].to_numpy(dtype=float)),   # STEP 14 interaction_weight
                    observed["weight"].to_numpy(dtype=float))              # belongs_to 1.0, has_topic topic weight
    fwd = pd.DataFrame({"source": observed["source"].to_numpy(), "target": observed["target"].to_numpy(),
                        "relation": observed["relation"].to_numpy(), "direction": "forward",
                        "kind": "observed", "weight": base})
    rev = fwd.assign(source=fwd["target"], target=fwd["source"], direction="reverse", kind="derived_diffusion_edge")
    edges = pd.concat([fwd, rev], ignore_index=True)
    edges["weight"] = edges["weight"] * [multipliers.get(f"{r}:{d}", 1.0)
                                         for r, d in zip(edges["relation"], edges["direction"])]
    edges = edges[edges["weight"] > 0].sort_values(["source", "relation", "direction", "target"],
                                                     kind="stable").reset_index(drop=True)

    if config.transition_rule == "weight_proportional":
        totals = edges.groupby("source")["weight"].transform("sum")
        prob = edges["weight"] / totals
    else:  # relation_balanced: equal share per (relation, direction) group at each node, then w/sum in group
        group = edges["relation"] + ":" + edges["direction"]
        group_tot = edges.groupby(["source", group])["weight"].transform("sum")
        n_groups = edges.assign(_g=group).groupby("source")["_g"].transform("nunique")
        prob = (edges["weight"] / group_tot) / n_groups
    edges = edges.assign(probability=prob.to_numpy())

    n = len(node_ids)
    rows = edges["source"].map(index).to_numpy()
    cols = edges["target"].map(index).to_numpy()
    transition = sparse.csr_matrix((edges["probability"].to_numpy(), (rows, cols)), shape=(n, n))
    out_mass = np.asarray(transition.sum(axis=1)).ravel()
    return DiffusionGraph(node_ids, nodes["node_type"].to_numpy(), transition, edges, out_mass == 0)


# --- personalized pagerank ------------------------------------------------------------------

def personalization_vector(dg: DiffusionGraph, graph: hg.HeteroGraph, source_channel_node: str,
                           mode: str) -> np.ndarray:
    idx = dg.index
    if source_channel_node not in idx or dg.node_types[idx[source_channel_node]] != "channel":
        raise DiffusionError(f"source {source_channel_node!r} is not a channel node of the graph")
    p = np.zeros(len(dg.node_ids))
    if mode == "source_channel":
        p[idx[source_channel_node]] = 1.0
    elif mode == "source_channel_videos":
        belongs = graph.edges_of("belongs_to")
        vids = sorted(belongs.loc[belongs["target"] == source_channel_node, "source"])
        if not vids:
            raise DiffusionError(f"{source_channel_node} has no videos for 'source_channel_videos' personalization")
        p[[idx[v] for v in vids]] = 1.0 / len(vids)
    else:
        raise DiffusionError("personalization must be 'source_channel' or 'source_channel_videos'")
    return p


def personalized_pagerank(dg: DiffusionGraph, p: np.ndarray, config: PPRConfig) -> tuple[np.ndarray, dict[str, Any]]:
    """Sparse power iteration; dangling mass is returned to the personalization vector."""
    if not 0 < config.alpha < 1:
        raise DiffusionError("alpha (damping) must be in (0, 1)")
    if not np.isclose(p.sum(), 1.0) or (p < 0).any():
        raise DiffusionError("personalization vector must be non-negative and sum to 1")
    pt = dg.transition.T.tocsr()
    r = p.copy()
    residual = float("inf")
    for it in range(1, config.max_iterations + 1):
        dangling_mass = r[dg.dangling].sum()
        new = (1 - config.alpha) * p + config.alpha * (pt @ r + dangling_mass * p)
        residual = float(np.abs(new - r).sum())
        r = new
        if residual < config.tolerance:
            return r, {"converged": True, "iterations": it, "residual": residual}
    return r, {"converged": False, "iterations": config.max_iterations, "residual": residual}


def reachable_from(dg: DiffusionGraph, start: list[int]) -> np.ndarray:
    """Nodes reachable from the start nodes along transitions (BFS on the sparse matrix)."""
    seen = np.zeros(len(dg.node_ids), dtype=bool)
    frontier = np.array(start)
    seen[frontier] = True
    t = dg.transition
    while len(frontier):
        nxt = np.unique(t[frontier].indices)
        nxt = nxt[~seen[nxt]]
        seen[nxt] = True
        frontier = nxt
    return seen


# --- source-channel analysis -------------------------------------------------------------------

def run_diffusion(graph: hg.HeteroGraph, config: PPRConfig = PPRConfig(),
                  sources: list[str] | None = None) -> DiffusionRun:
    """PPR from each source channel (default: every channel with outgoing transitions).

    Results are kept per source: one row per (source, destination) channel pair.
    """
    dg = build_diffusion_graph(graph, config)
    idx = dg.index
    channels = [n for n, t in zip(dg.node_ids, dg.node_types) if t == "channel"]
    if sources is None:
        sources = [c for c in channels if not dg.dangling[idx[c]]]
    unknown = [s for s in sources if s not in idx or dg.node_types[idx[s]] != "channel"]
    if unknown:
        raise DiffusionError(f"unknown source channel(s): {unknown}")
    skipped = {c: "no stored videos: nothing to diffuse from" for c in channels
               if dg.dangling[idx[c]] and c not in sources}

    experiment_id = make_experiment_id(graph, config)
    chan_idx = np.array([idx[c] for c in channels])
    frames, convergence = [], {}
    for src in sorted(sources):
        p = personalization_vector(dg, graph, src, config.personalization)
        r, conv = personalized_pagerank(dg, p, config)
        convergence[src] = {**conv, "total_mass": float(r.sum())}
        reach = reachable_from(dg, list(np.flatnonzero(p)))
        df = pd.DataFrame({"destination_channel_id": channels, "diffusion_score": r[chan_idx],
                           "reachable": reach[chan_idx]})
        df["is_source"] = df["destination_channel_id"] == src
        if not config.include_source:
            df = df[~df["is_source"]]
        total = df["diffusion_score"].sum()
        df["normalized_destination_share"] = df["diffusion_score"] / total if total > 0 else np.nan
        df = df.sort_values(["diffusion_score", "destination_channel_id"], ascending=[False, True], kind="stable")
        df["rank"] = np.arange(1, len(df) + 1)
        df["source_channel_id"] = src
        frames.append(df)

    results = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=list(RESULT_COLUMNS))
    results = results.assign(snapshot_id=graph.snapshot_id, experiment_id=experiment_id)
    results = results[list(RESULT_COLUMNS)].astype(RESULT_COLUMNS).reset_index(drop=True)

    run = DiffusionRun(graph.snapshot_id, experiment_id, results)
    run.metadata = {
        "method": METHOD, "method_version": METHOD_VERSION, "experiment_id": experiment_id,
        "snapshot_id": graph.snapshot_id, "graph_fingerprint": graph.fingerprint(),
        "graph_schema_version": hg.GRAPH_SCHEMA_VERSION, "edge_weighting_version": EDGE_WEIGHTING_VERSION,
        "config": config.to_dict(),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "versions": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
        "diffusion_graph": {
            "nodes": len(dg.node_ids), "edges": int(len(dg.edges)),
            "observed_edges": int((dg.edges["kind"] == "observed").sum()),
            "derived_diffusion_edges": int((dg.edges["kind"] == "derived_diffusion_edge").sum()),
            "dangling_nodes": int(dg.dangling.sum()),
            "dangling_handling": "dangling mass is returned to the personalization vector (the source)",
        },
        "sources": sorted(sources), "skipped_sources": skipped, "convergence": convergence,
        "note": "diffusion_score is a graph diffusion / structural connectivity signal (a potential audience "
                "bridge signal), not an Audience Bridge Score; it does not show audience migration, causality, "
                "subscriber movement, conversion or guaranteed growth.",
    }
    run.metadata["validation"] = validate(run, dg, graph, config)
    return run


def make_experiment_id(graph: hg.HeteroGraph, config: PPRConfig) -> str:
    payload = json.dumps({"graph": graph.fingerprint(), "config": config.to_dict(), "method": METHOD_VERSION,
                          "weights": EDGE_WEIGHTING_VERSION}, sort_keys=True)
    return f"ppr-{hashlib.sha256(payload.encode()).hexdigest()[:12]}"


# --- validation ------------------------------------------------------------------------------

def validate(run: DiffusionRun, dg: DiffusionGraph, graph: hg.HeteroGraph, config: PPRConfig) -> dict[str, Any]:
    errors = []
    row_sums = np.asarray(dg.transition.sum(axis=1)).ravel()
    if not np.allclose(row_sums[~dg.dangling], 1.0, atol=1e-9):
        errors.append("transition rows do not sum to 1")
    if (dg.transition.data < 0).any():
        errors.append("negative transition probabilities")
    r = run.results
    channels = set(graph.nodes.loc[graph.nodes["node_type"] == "channel", "node_id"])
    if not set(r["source_channel_id"]) <= channels or not set(r["destination_channel_id"]) <= channels:
        errors.append("results reference channels that are not in the graph")
    if not np.isfinite(r["diffusion_score"]).all() or (r["diffusion_score"] < 0).any():
        errors.append("diffusion scores must be finite and non-negative")
    for src, conv in run.metadata["convergence"].items():
        if not np.isclose(conv["total_mass"], 1.0, atol=1e-6):
            errors.append(f"{src}: PageRank mass {conv['total_mass']} does not sum to 1")
    if r.duplicated(["source_channel_id", "destination_channel_id"]).any():
        errors.append("duplicate (source, destination) rows")
    if not config.include_source and r["is_source"].any():
        errors.append("source channel present although include_source is False")
    if (r.loc[~r["reachable"], "diffusion_score"] > 1e-12).any():
        errors.append("unreachable destinations received diffusion mass")
    if any(not str(x).startswith("channel:") for x in pd.concat([r["source_channel_id"], r["destination_channel_id"]])):
        errors.append("non-channel ids in channel results")
    if errors:
        raise DiffusionError("diffusion validation failed: " + "; ".join(errors))
    return {"passed": True, "transition_rows_stochastic": True, "mass_conserved": True,
            "not_converged_sources": [s for s, c in run.metadata["convergence"].items() if not c["converged"]]}


# --- persistence ---------------------------------------------------------------------------

def diffusion_dir(snapshot_id: str, experiment_id: str) -> Path:
    return hg.graph_dir(snapshot_id).parent / DIFFUSION_DIR / experiment_id


def save_run(run: DiffusionRun) -> Path:
    target = diffusion_dir(run.snapshot_id, run.experiment_id)
    if (target / "diffusion_run.json").is_file():
        existing = load_run(target)
        if existing.results.equals(run.results):
            return target
        raise FileExistsError(f"diffusion experiment {run.experiment_id} already exists with different results")
    staging = target.with_name(f".{target.name}.staging")
    write_dataset(run.results, staging / "channel_diffusion.parquet", overwrite=True)
    meta = {**run.metadata, "results_sha256": _digest(run.results)}
    (staging / "diffusion_run.json").write_text(json.dumps(meta, indent=2, default=str) + "\n", encoding="utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging, target)
    return target


def load_run(directory: Path) -> DiffusionRun:
    meta = json.loads((directory / "diffusion_run.json").read_text(encoding="utf-8"))
    results = read_dataset(directory / "channel_diffusion.parquet").astype(RESULT_COLUMNS)
    if _digest(results) != meta.get("results_sha256"):
        raise DiffusionError("channel_diffusion.parquet changed after saving (checksum mismatch)")
    return DiffusionRun(meta["snapshot_id"], meta["experiment_id"], results, meta)


def _digest(df: pd.DataFrame) -> str:
    return hashlib.sha256(df.to_csv(index=False, float_format="%.15g").encode()).hexdigest()


# --- command line ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse

    d = PPRConfig()
    ap = argparse.ArgumentParser(prog="ppr_diffusion", description="Personalized PageRank diffusion (Component 3).")
    ap.add_argument("--snapshot", help="research snapshot id (default: latest)")
    ap.add_argument("--source", action="append", help="source channel id (repeatable; default: all eligible)")
    ap.add_argument("--alpha", type=float, default=d.alpha)
    ap.add_argument("--transition-rule", choices=["weight_proportional", "relation_balanced"], default=d.transition_rule)
    ap.add_argument("--include-source", action="store_true")
    args = ap.parse_args(argv)
    try:
        sid = args.snapshot or snapshots.latest_research_snapshot().snapshot_id
        path = hg.graph_dir(sid)
        graph = hg.load_graph(path) if (path / hg.MANIFEST_FILE).is_file() else hg.build_graph(sid)
        cfg = PPRConfig(alpha=args.alpha, transition_rule=args.transition_rule, include_source=args.include_source)
        sources = [s if s.startswith("channel:") else f"channel:{s}" for s in args.source] if args.source else None
        run = run_diffusion(graph, cfg, sources)
        out = save_run(run)
    except (DiffusionError, FileExistsError, hg.GraphBuildError, snapshots.SnapshotNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    md = run.metadata
    conv = md["convergence"]
    print(f"PPR diffusion {run.experiment_id} on {sid} saved to {out}")
    print(f"  sources {len(md['sources'])} (skipped {len(md['skipped_sources'])}); all converged: "
          f"{all(c['converged'] for c in conv.values())}; max iterations {max((c['iterations'] for c in conv.values()), default=0)}")
    for src in md["sources"][:3]:
        top = run.results[run.results["source_channel_id"] == src].head(3)
        print(f"  {src} -> " + ", ".join(f"{r.destination_channel_id} ({r.diffusion_score:.2e}, reach={r.reachable})"
                                         for r in top.itertuples()))
    print("  (diffusion_score = structural connectivity signal; not an Audience Bridge Score)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
