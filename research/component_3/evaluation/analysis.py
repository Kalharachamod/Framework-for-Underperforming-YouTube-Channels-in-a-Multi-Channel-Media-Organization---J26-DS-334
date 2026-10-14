"""Comparisons of standard ranking tables: relevance metrics (labels only), agreement, top-k.

All per-source values are macro-averaged over the sources where the value is defined;
``n_sources`` says how many sources contributed. Undefined aggregates are NULL with a reason.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd

from research.component_3.evaluation import metrics as mt

RESULT_FIELDS = ["metric", "k", "value", "n_sources", "status", "reason"]
LABEL_COLUMNS = ["source_channel_id", "destination_channel_id", "relevance", "label_source"]
TOP_K_COLUMNS = ["method", "experiment_id", "source_channel_id", "rank", "destination_channel_id", "score",
                 "tied", "boundary_tie_at_k"]


class EvaluationError(ValueError):
    pass


# --- helpers ------------------------------------------------------------------------------------

def ranked_list(group: pd.DataFrame) -> list[str]:
    """Destinations with a defined score, in rank order."""
    g = group.dropna(subset=["rank"]).sort_values("rank")
    return g["destination_channel_id"].astype(str).tolist()


def score_map(group: pd.DataFrame) -> dict[str, float]:
    g = group.dropna(subset=["score"])
    return dict(zip(g["destination_channel_id"].astype(str), g["score"].astype(float)))


def aggregate(metric: str, k: int | None, values: list[float | None], reasons: list[str | None]) -> dict:
    defined = [v for v in values if v is not None]
    if not defined:
        why = Counter(r for r in reasons if r).most_common(1)
        return {"metric": metric, "k": k, "value": None, "n_sources": 0, "status": "undefined",
                "reason": why[0][0] if why else "no sources to evaluate"}
    return {"metric": metric, "k": k, "value": float(np.mean(defined)), "n_sources": len(defined),
            "status": "ok", "reason": None}


def _by_source(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {str(s): g for s, g in df.groupby("source_channel_id", sort=True)}


# --- agreement between two rankings (no labels needed) -------------------------------------------

def compare_rankings(a: pd.DataFrame, b: pd.DataFrame, ks: Sequence[int]) -> list[dict]:
    """Per-source Spearman, Kendall tau-b and top-k Jaccard between two ranking tables, macro-averaged
    over sources ranked by both. Used for method agreement, temporal stability and sparse robustness."""
    ga, gb = _by_source(a), _by_source(b)
    sources = sorted(set(ga) & set(gb))
    rows = []
    for method in ("spearman", "kendall"):
        vals, why = [], []
        for s in sources:
            v, _, reason = mt.rank_correlation(score_map(ga[s]), score_map(gb[s]), method)
            vals.append(v)
            why.append(reason)
        rows.append(aggregate(method, None, vals, why or ["no source ranked by both"]))
    for k in ks:
        vals = [mt.topk_jaccard(ranked_list(ga[s]), ranked_list(gb[s]), k) for s in sources]
        rows.append(aggregate("topk_jaccard", k, vals, ["no ranked destinations"] * len(vals) or
                              ["no source ranked by both"]))
    return rows


# --- relevance metrics (explicit labels only) ----------------------------------------------------

def load_labels(path: str | Path, channels: Sequence[str]) -> tuple[pd.DataFrame, str]:
    """Read and validate an explicit relevance-label file (CSV or Parquet). Returns (labels, sha256)."""
    p = Path(path)
    if not p.is_file():
        raise EvaluationError(f"label file not found: {p}")
    df = pd.read_parquet(p) if p.suffix.lower() == ".parquet" else pd.read_csv(p)
    return validate_labels(df, channels), hashlib.sha256(p.read_bytes()).hexdigest()


def validate_labels(df: pd.DataFrame, channels: Sequence[str]) -> pd.DataFrame:
    """Labels must be explicit and well formed; anything doubtful is refused rather than guessed."""
    missing = [c for c in LABEL_COLUMNS if c not in df.columns]
    if missing:
        raise EvaluationError(f"labels are missing column(s) {missing}; required {LABEL_COLUMNS}")
    df = df[LABEL_COLUMNS].copy()
    if df.empty:
        raise EvaluationError("label file has no rows")
    if df[["source_channel_id", "destination_channel_id"]].isna().any().any():
        raise EvaluationError("labels contain empty channel ids")
    df["source_channel_id"] = df["source_channel_id"].astype(str)
    df["destination_channel_id"] = df["destination_channel_id"].astype(str)
    if df["label_source"].isna().any() or (df["label_source"].astype(str).str.strip() == "").any():
        raise EvaluationError("every label needs a non-empty label_source (where the judgement came from)")
    rel = pd.to_numeric(df["relevance"], errors="coerce")
    if rel.isna().any() or not np.isfinite(rel).all() or (rel < 0).any():
        raise EvaluationError("relevance must be a finite, non-negative number on every row")
    df["relevance"] = rel.astype(float)
    known = set(channels)
    unknown = sorted((set(df["source_channel_id"]) | set(df["destination_channel_id"])) - known)
    if unknown:
        raise EvaluationError(f"labels reference channels not in the snapshot: {unknown[:5]}")
    if (df["source_channel_id"] == df["destination_channel_id"]).any():
        raise EvaluationError("labels contain self pairs")
    if df.duplicated(["source_channel_id", "destination_channel_id"]).any():
        raise EvaluationError("labels contain duplicate (source, destination) pairs")
    return df.sort_values(["source_channel_id", "destination_channel_id"]).reset_index(drop=True)


def relevance_metrics(rankings: pd.DataFrame, labels: pd.DataFrame, ks: Sequence[int]) -> list[dict]:
    """Precision@k, Recall@k, NDCG@k and MRR over the labelled sources.

    Labelled sources are treated as fully judged: an unlabelled destination counts as not relevant.
    A destination is relevant when its relevance > 0; NDCG uses the graded relevance as gain.
    """
    gr = _by_source(rankings)
    rows = []
    sources = sorted(set(labels["source_channel_id"]))
    judged = {s: g for s, g in labels.groupby("source_channel_id")}
    lists = {s: ranked_list(gr[s]) if s in gr else [] for s in sources}
    gains = {s: dict(zip(judged[s]["destination_channel_id"], judged[s]["relevance"])) for s in sources}
    relevant = {s: {d for d, g in gains[s].items() if g > 0} for s in sources}
    for k in ks:
        for name, fn in (("precision", lambda s: mt.precision_at_k(lists[s], relevant[s], k)),
                         ("recall", lambda s: mt.recall_at_k(lists[s], relevant[s], k)),
                         ("ndcg", lambda s: mt.ndcg_at_k(lists[s], gains[s], k))):
            vals = [fn(s) for s in sources]
            rows.append(aggregate(f"{name}_at_k", k, vals, ["no relevant or ranked items for the source"] * len(vals)))
    vals = [mt.reciprocal_rank(lists[s], relevant[s]) for s in sources]
    rows.append(aggregate("mrr", None, vals, ["no relevant items for the source"] * len(vals)))
    return rows


# --- top-k tables ----------------------------------------------------------------------------------

def top_k_table(rankings: pd.DataFrame, ks: Sequence[int]) -> pd.DataFrame:
    """Rows of rank <= max(k) per source (self pairs and NULL scores never appear).

    boundary_tie_at_k lists the k values where this row's score ties with a destination just
    outside the top k, i.e. the top-k membership there depends on the tie-break rule.
    """
    kmax = max(ks)
    out = []
    for (method, src), g in rankings.dropna(subset=["rank"]).groupby(["method", "source_channel_id"], sort=True):
        g = g.sort_values("rank")
        scores = g["score"].tolist()
        top = g[g["rank"] <= kmax].copy()
        ties = []
        for r, sc in zip(top["rank"], top["score"]):
            hit = [str(k) for k in ks if r <= k < len(scores) and scores[k] == sc]
            ties.append(",".join(hit) or None)
        top["boundary_tie_at_k"] = ties
        out.append(top)
    if not out:
        return pd.DataFrame(columns=TOP_K_COLUMNS)
    return pd.concat(out, ignore_index=True)[TOP_K_COLUMNS]


def top_k_summary(rankings: pd.DataFrame, ks: Sequence[int]) -> list[dict]:
    """Distinct destinations across all sources' top-k (low = a few hubs dominate every list) and the
    share of sources whose top-k boundary falls inside a tie."""
    rows = []
    lists = {s: (ranked_list(g), g.dropna(subset=["rank"]).sort_values("rank")["score"].tolist())
             for s, g in _by_source(rankings).items()}
    for k in ks:
        tops = [lst[:k] for lst, _ in lists.values() if lst]
        if not tops:
            rows.append({"metric": "topk_distinct_destinations", "k": k, "value": None, "n_sources": 0,
                         "status": "undefined", "reason": "no ranked destinations"})
            rows.append({"metric": "topk_boundary_tie_share", "k": k, "value": None, "n_sources": 0,
                         "status": "undefined", "reason": "no ranked destinations"})
            continue
        rows.append({"metric": "topk_distinct_destinations", "k": k, "value": float(len(set().union(*tops))),
                     "n_sources": len(tops), "status": "ok", "reason": None})
        tied = [len(sc) > k and sc[k - 1] == sc[k] for lst, sc in lists.values() if lst]
        rows.append({"metric": "topk_boundary_tie_share", "k": k, "value": float(np.mean(tied)),
                     "n_sources": len(tied), "status": "ok", "reason": None})
    return rows
