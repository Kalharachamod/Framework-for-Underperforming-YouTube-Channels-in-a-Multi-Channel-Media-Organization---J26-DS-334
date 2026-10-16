"""Deterministic blinded human-review sampling."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from .audit import HUMAN_REVIEW_COLUMNS


def _stable_hash(value: object, seed: int) -> str:
    return hashlib.sha256(f"{seed}:{value}".encode("utf-8")).hexdigest()


def make_blinded_review_sample(
    frame: pd.DataFrame,
    predictions: pd.DataFrame,
    *,
    seed: int,
    candidate_per_channel: int = 10,
    control_per_channel: int = 10,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return a blinded review CSV and a separate local-only sampling manifest."""

    if len(frame) != len(predictions):
        raise ValueError("Frame and prediction row counts must match")
    working = frame.reset_index(drop=True).copy()
    predicted = predictions.reset_index(drop=True).copy()
    if "comment_id" not in predicted:
        predicted["comment_id"] = working["comment_id"]
    joined = pd.concat([working, predicted], axis=1)
    joined = joined.loc[:, ~joined.columns.duplicated()]
    joined["_stable"] = joined["comment_id"].map(lambda value: _stable_hash(value, seed))

    selected: list[pd.DataFrame] = []
    manifest: list[dict[str, object]] = []
    for channel_name, channel_group in joined.groupby("channel_name", sort=True, dropna=False):
        candidates = channel_group[channel_group["candidate_for_content_demand"]].sort_values(
            ["baseline_score", "_stable", "comment_id"], ascending=[False, True, True]
        )
        controls = channel_group[~channel_group["candidate_for_content_demand"]].sort_values(
            ["_stable", "comment_id"]
        )
        for group_name, chosen in (
            ("candidate", candidates.head(candidate_per_channel)),
            ("control", controls.head(control_per_channel)),
        ):
            for _, row in chosen.iterrows():
                review_id = f"review_{len(manifest) + 1:03d}"
                selected.append(row.to_frame().T)
                manifest.append(
                    {
                        "review_id": review_id,
                        "comment_id": row["comment_id"],
                        "channel_name": row["channel_name"],
                        "review_group": group_name,
                        "baseline_primary_signal": row["primary_signal"],
                        "baseline_score": int(row["baseline_score"]),
                        "candidate_for_content_demand": bool(row["candidate_for_content_demand"]),
                        "sampling_seed": seed,
                    }
                )

    if not selected:
        raise ValueError("No review rows were selected")
    selected_frame = pd.concat(selected, ignore_index=True)
    manifest_frame = pd.DataFrame(manifest)
    selected_frame["review_id"] = manifest_frame["review_id"].tolist()
    selected_frame["review_order"] = range(1, len(selected_frame) + 1)

    review_columns = [
        "review_order", "review_id", "comment_id", "channel_id", "channel_name", "channel_type",
        "video_id", "video_title", "video_description", "video_url", "parent_comment_text",
        "original_text", "cleaned_text", "script_category", "sampling_stratum",
    ]
    review = selected_frame[[column for column in review_columns if column in selected_frame]].copy()
    for column in HUMAN_REVIEW_COLUMNS:
        review[column] = ""
    return review, manifest_frame


def write_review_outputs(review: pd.DataFrame, manifest: pd.DataFrame, output_dir: str | Path) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    review.to_csv(output / "human_review_sample.csv", index=False, encoding="utf-8")
    manifest.to_csv(output / "review_manifest.csv", index=False, encoding="utf-8")
