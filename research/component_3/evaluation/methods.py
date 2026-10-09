"""Method adapters: each method -> one standard channel-ranking table for a snapshot.

Standard ranking columns:
  method, role, signal_type, source_channel_id, destination_channel_id, score, rank,
  tied, snapshot_id, experiment_id

* score: the method's own signal (higher = stronger); NULL when undefined (never 0).
* rank: 1 = strongest per source; ties broken by destination_channel_id; NULL if score is NULL.
* tied: another destination of the same source has the identical score.

Methods:
  audience_bridge_score  proposed (STEP 19)   - slot; "unavailable" until implemented
  ppr_diffusion          component of proposed (STEP 17 diffusion_score)
  topic_similarity       component of proposed (STEP 18 topic_similarity, symmetric)
  louvain                baseline (STEP 20 binary same-community indicator)
  node2vec               baseline (STEP 20 raw cosine similarity)
"""

from __future__ import annotations

import importlib
import time
import tracemalloc
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

RANKING_COLUMNS = ["method", "role", "signal_type", "source_channel_id", "destination_channel_id", "score",
                   "rank", "tied", "snapshot_id", "experiment_id"]
ABS_MODULE = "research.component_3.model.audience_bridge"   # expected STEP 19 module


@dataclass
class MethodRun:
    method: str
    status: str                          # "ok" | "unavailable" | "failed"
    rankings: pd.DataFrame
    experiment_id: str | None = None
    reason: str | None = None
    seconds: float | None = None
    python_peak_mib: float | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class MethodContext:
    """Everything the adapters need for one snapshot (built once, shared)."""

    snapshot_id: str
    baseline_input: Any                  # baselines.BaselineInput (graph, channels, pair features)
    encoder: Any = None                  # topic encoder (None -> e5)
    node2vec_config: Any = None
    louvain_config: Any = None
    ppr_config: Any = None
    topic_config: Any = None


def standardize(raw: pd.DataFrame, *, method: str, role: str, signal_type: str, score_col: str,
                snapshot_id: str, experiment_id: str, channels: list[str]) -> pd.DataFrame:
    """Turn a method output into the standard ranking table (deterministic ordering)."""
    df = raw[["source_channel_id", "destination_channel_id", score_col]].rename(columns={score_col: "score"}).copy()
    df["score"] = pd.to_numeric(df["score"], errors="coerce").astype("float64")
    df = df[df["source_channel_id"] != df["destination_channel_id"]]
    df = df[df["source_channel_id"].isin(channels) & df["destination_channel_id"].isin(channels)]
    df = df.sort_values(["source_channel_id", "score", "destination_channel_id"], ascending=[True, False, True],
                        na_position="last", kind="stable").reset_index(drop=True)
    df["rank"] = df.groupby("source_channel_id")["score"].rank(method="first", ascending=False).astype("Int64")
    df["tied"] = df.duplicated(["source_channel_id", "score"], keep=False) & df["score"].notna()
    df = df.assign(method=method, role=role, signal_type=signal_type, snapshot_id=snapshot_id,
                   experiment_id=experiment_id)
    return df[RANKING_COLUMNS]


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=RANKING_COLUMNS)


def _ppr(ctx: MethodContext) -> tuple[pd.DataFrame, str, dict]:
    from research.component_3.model import ppr_diffusion as ppr

    inp = ctx.baseline_input
    run = ppr.run_diffusion(inp.graph, ctx.ppr_config or ppr.PPRConfig())
    df = standardize(run.results, method="ppr_diffusion", role="component of proposed method",
                     signal_type="graded", score_col="diffusion_score", snapshot_id=inp.snapshot_id,
                     experiment_id=run.experiment_id, channels=inp.channels)
    return df, run.experiment_id, {"reachable_pairs": int(run.results["reachable"].sum())}


def _topic(ctx: MethodContext) -> tuple[pd.DataFrame, str, dict]:
    from research.component_3.model import topic_similarity as ts

    inp = ctx.baseline_input
    r = ts.run(inp.snapshot_id, ctx.topic_config or ts.TopicConfig(), encoder=ctx.encoder)
    df = standardize(r.similarity, method="topic_similarity", role="component of proposed method",
                     signal_type="graded", score_col="topic_similarity", snapshot_id=inp.snapshot_id,
                     experiment_id=r.experiment_id, channels=inp.channels)
    return df, r.experiment_id, {"channels_with_profile": r.metadata["coverage"]["channels_with_profile"]}


def _louvain(ctx: MethodContext) -> tuple[pd.DataFrame, str, dict]:
    from research.component_3.model import baselines as bl

    inp = ctx.baseline_input
    r = bl.run_louvain(inp, ctx.louvain_config or bl.LouvainConfig())
    df = standardize(r.relationships, method="louvain", role="baseline",
                     signal_type="binary (same community = 1)", score_col="community_relationship",
                     snapshot_id=inp.snapshot_id, experiment_id=r.experiment_id, channels=inp.channels)
    return df, r.experiment_id, {"communities": r.metadata["communities"], "modularity": r.metadata["modularity"]}


def _node2vec(ctx: MethodContext) -> tuple[pd.DataFrame, str, dict]:
    from research.component_3.model import baselines as bl

    inp = ctx.baseline_input
    r = bl.run_node2vec(inp, ctx.node2vec_config or bl.Node2VecConfig())
    df = standardize(r.similarity, method="node2vec", role="baseline", signal_type="graded",
                     score_col="raw_node2vec_similarity", snapshot_id=inp.snapshot_id,
                     experiment_id=r.experiment_id, channels=inp.channels)
    return df, r.experiment_id, {"embedded_nodes": int(len(r.embeddings.nodes))}


def _abs(ctx: MethodContext) -> tuple[pd.DataFrame, str, dict]:
    """Slot for the proposed Audience Bridge Score (STEP 19). Uses ``score_channels(ctx)`` from
    ABS_MODULE when it exists, which must return (raw table with an 'audience_bridge_score'
    column, experiment_id)."""
    module = importlib.import_module(ABS_MODULE)  # ModuleNotFoundError -> "unavailable"
    raw, experiment_id = module.score_channels(ctx)
    inp = ctx.baseline_input
    df = standardize(raw, method="audience_bridge_score", role="proposed method", signal_type="graded",
                     score_col="audience_bridge_score", snapshot_id=inp.snapshot_id,
                     experiment_id=experiment_id, channels=inp.channels)
    return df, experiment_id, {}


METHODS: dict[str, Callable[[MethodContext], tuple[pd.DataFrame, str, dict]]] = {
    "audience_bridge_score": _abs,
    "ppr_diffusion": _ppr,
    "topic_similarity": _topic,
    "louvain": _louvain,
    "node2vec": _node2vec,
}
PROPOSED = ("audience_bridge_score",)
PROPOSED_COMPONENTS = ("ppr_diffusion", "topic_similarity")
BASELINES = ("louvain", "node2vec")


def run_method(name: str, ctx: MethodContext) -> MethodRun:
    """Run one method with a measured boundary: wall-clock time and Python-heap peak (tracemalloc)."""
    if name not in METHODS:
        raise ValueError(f"unknown method {name!r}; available: {sorted(METHODS)}")
    already = tracemalloc.is_tracing()
    if already:
        tracemalloc.reset_peak()
    else:
        tracemalloc.start()
    t0 = time.perf_counter()
    try:
        df, experiment_id, details = METHODS[name](ctx)
        status, reason = "ok", None
    except ModuleNotFoundError as exc:
        if name == "audience_bridge_score" and getattr(exc, "name", "") == ABS_MODULE:
            df, experiment_id, details = _empty(), None, {}
            status, reason = "unavailable", "Audience Bridge Score (STEP 19) is not implemented yet"
        else:
            raise
    except (ValueError, RuntimeError) as exc:
        df, experiment_id, details = _empty(), None, {}
        status, reason = "failed", f"{type(exc).__name__}: {str(exc).splitlines()[0][:300]}"
    seconds = time.perf_counter() - t0
    _, peak = tracemalloc.get_traced_memory()
    if not already:
        tracemalloc.stop()
    return MethodRun(name, status, df, experiment_id, reason, round(seconds, 4), round(peak / 2**20, 3), details)


def validate_rankings(df: pd.DataFrame) -> list[str]:
    errors = []
    if list(df.columns) != RANKING_COLUMNS:
        return ["ranking table does not have the standard columns"]
    if (df["source_channel_id"] == df["destination_channel_id"]).any():
        errors.append("self-channel pairs present")
    if df.duplicated(["method", "snapshot_id", "source_channel_id", "destination_channel_id"]).any():
        errors.append("duplicate (source, destination) pairs")
    sc = df["score"].dropna()
    if len(sc) and not np.isfinite(sc.astype(float)).all():
        errors.append("non-finite scores")
    for (_, _, _src), g in df.groupby(["method", "snapshot_id", "source_channel_id"]):
        ranked = g.dropna(subset=["rank"]).sort_values("rank")
        if list(ranked["rank"]) != list(range(1, len(ranked) + 1)):
            errors.append("ranks are not 1..n per source")
            break
        if (ranked["score"].diff().dropna() > 1e-12).any():
            errors.append("ranks are not ordered by descending score")
            break
    return errors
