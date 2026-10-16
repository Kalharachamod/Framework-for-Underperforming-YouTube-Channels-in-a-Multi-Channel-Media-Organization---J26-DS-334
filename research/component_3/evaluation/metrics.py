"""Ranking metrics for the Component 3 evaluation framework.

Every function returns ``None`` when the metric is undefined (e.g. no relevant
items, fewer than 3 shared items, constant rankings); undefined is never 0.

Relevance-based metrics (precision@k, recall@k, NDCG@k, reciprocal rank) need
explicit relevance labels; the framework refuses to run them without labels.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np


def precision_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float | None:
    """|top-k ∩ relevant| / k  (k is capped at the number of ranked items; None if none)."""
    _check_k(k)
    top = list(ranked)[:k]
    if not top:
        return None
    return sum(1 for d in top if d in relevant) / len(top)


def recall_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float | None:
    """|top-k ∩ relevant| / |relevant|; None when there are no relevant items."""
    _check_k(k)
    if not relevant:
        return None
    return sum(1 for d in list(ranked)[:k] if d in relevant) / len(relevant)


def ndcg_at_k(ranked: Sequence[str], gains: dict[str, float], k: int) -> float | None:
    """DCG@k / ideal DCG@k with graded gains (rel / log2(rank + 1)); None if the ideal DCG is 0."""
    _check_k(k)
    if any(g < 0 or not math.isfinite(g) for g in gains.values()):
        raise ValueError("relevance gains must be finite and non-negative")
    dcg = sum(gains.get(d, 0.0) / math.log2(i + 2) for i, d in enumerate(list(ranked)[:k]))
    ideal = sorted((g for g in gains.values() if g > 0), reverse=True)[:k]
    idcg = sum(g / math.log2(i + 2) for i, g in enumerate(ideal))
    return None if idcg == 0 else dcg / idcg


def reciprocal_rank(ranked: Sequence[str], relevant: set[str]) -> float | None:
    """1 / rank of the first relevant item; 0.0 if relevant items exist but none is ranked;
    None if there are no relevant items."""
    if not relevant:
        return None
    for i, d in enumerate(ranked):
        if d in relevant:
            return 1.0 / (i + 1)
    return 0.0


def rank_correlation(a: dict[str, float], b: dict[str, float], method: str = "spearman") -> tuple[float | None, int, str | None]:
    """Correlation of two score maps over their common keys with defined (finite) scores.

    Returns (value, n_common, reason_if_undefined). Ties are handled by average ranks
    (Spearman) / tau-b (Kendall). Undefined for < 3 common items or a constant ranking.
    """
    from scipy.stats import kendalltau, spearmanr

    if method not in ("spearman", "kendall"):
        raise ValueError("method must be 'spearman' or 'kendall'")
    common = sorted(k for k in set(a) & set(b) if _finite(a[k]) and _finite(b[k]))
    n = len(common)
    if n < 3:
        return None, n, "fewer than 3 common items with defined scores"
    x, y = np.array([a[k] for k in common]), np.array([b[k] for k in common])
    if np.all(x == x[0]) or np.all(y == y[0]):
        return None, n, "constant scores in one ranking"
    value = (spearmanr(x, y) if method == "spearman" else kendalltau(x, y)).statistic
    return (float(value), n, None) if math.isfinite(value) else (None, n, "undefined correlation")


def topk_jaccard(a: Sequence[str], b: Sequence[str], k: int) -> float | None:
    """|top-k(a) ∩ top-k(b)| / |top-k(a) ∪ top-k(b)|; None if both are empty."""
    _check_k(k)
    sa, sb = set(list(a)[:k]), set(list(b)[:k])
    union = sa | sb
    return None if not union else len(sa & sb) / len(union)


def _check_k(k: int) -> None:
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ValueError("k must be a positive integer")


def _finite(v) -> bool:
    try:
        return v is not None and math.isfinite(float(v))
    except (TypeError, ValueError):
        return False
