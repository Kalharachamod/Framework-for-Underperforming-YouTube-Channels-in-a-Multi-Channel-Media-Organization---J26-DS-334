"""Evaluation helpers for later human-reviewed feasibility results."""

from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd


def _normalise_binary(value: object) -> bool | None:
    if value is None or pd.isna(value):
        return None
    normalized = str(value).strip().casefold()
    if normalized in {"true", "yes", "1", "demand", "candidate"}:
        return True
    if normalized in {"false", "no", "0", "non_demand", "non-demand", "not_candidate"}:
        return False
    return None


def cohen_kappa(labels_a: list[object], labels_b: list[object]) -> float | None:
    """Calculate unweighted Cohen's kappa for two equal-length label lists."""

    pairs = [(a, b) for a, b in zip(labels_a, labels_b) if not pd.isna(a) and not pd.isna(b)]
    if not pairs:
        return None
    observed = sum(a == b for a, b in pairs) / len(pairs)
    counts_a = Counter(a for a, _ in pairs)
    counts_b = Counter(b for _, b in pairs)
    expected = sum((counts_a[label] / len(pairs)) * (counts_b[label] / len(pairs)) for label in set(counts_a) | set(counts_b))
    if expected == 1:
        return 1.0
    return (observed - expected) / (1 - expected)


def evaluate_review(
    review: pd.DataFrame,
    manifest: pd.DataFrame | None = None,
    *,
    representative: bool = False,
) -> dict[str, Any]:
    """Evaluate only rows with verified human labels.

    The function deliberately returns ``not_available`` until a reviewer has
    supplied the actionability field. It never treats heuristic predictions as
    ground truth.
    """

    if "human_actionable_content_demand" not in review:
        return {"status": "not_available", "reason": "human_verified_labels_are_required", "metrics": {}}
    labelled = review.copy()
    labelled["_human_actionable"] = labelled["human_actionable_content_demand"].map(_normalise_binary)
    labelled = labelled[labelled["_human_actionable"].notna()].copy()
    if labelled.empty:
        return {"status": "not_available", "reason": "human_verified_labels_are_required", "metrics": {}}

    if manifest is not None and "review_group" in manifest:
        labelled = labelled.merge(manifest[["review_id", "review_group"]], on="review_id", how="left")
    if "review_group" not in labelled:
        labelled["review_group"] = "unclassified"

    candidate_rows = labelled[labelled["review_group"] == "candidate"]
    true_candidates = labelled[labelled["_human_actionable"]]
    metrics: dict[str, Any] = {
        "labelled_rows": int(len(labelled)),
        "candidate_rows": int(len(candidate_rows)),
        "verified_candidate_count": int(candidate_rows["_human_actionable"].sum()),
        "candidate_precision": (
            float(candidate_rows["_human_actionable"].mean()) if len(candidate_rows) else None
        ),
        "candidate_yield": float(labelled["_human_actionable"].mean()),
        "false_positive_by_human_signal": {
            str(key): int(value)
            for key, value in labelled.loc[~labelled["_human_actionable"], "human_primary_signal"].value_counts(dropna=False).items()
        },
        "candidate_yield_by_channel": {
            str(key): int(value)
            for key, value in labelled[labelled["_human_actionable"]].groupby("channel_name").size().items()
        },
        "recall": None,
        "recall_note": "Only computed for a defensible representative review sample.",
    }
    if representative:
        metrics["recall"] = float(candidate_rows["_human_actionable"].sum() / len(true_candidates)) if len(true_candidates) else None

    paired_columns = ["human_primary_signal_annotator_1", "human_primary_signal_annotator_2"]
    if all(column in labelled for column in paired_columns):
        metrics["cohen_kappa_primary_signal"] = cohen_kappa(
            labelled[paired_columns[0]].tolist(), labelled[paired_columns[1]].tolist()
        )
    return {"status": "available", "metrics": metrics}
