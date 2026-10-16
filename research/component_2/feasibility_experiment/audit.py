"""Read-only dataset assembly and aggregate audit helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from research.component_2.src.data_io import load_comments, load_videos
from research.component_2.src.text_processing import preprocess_comment_text, script_features


CHANNEL_TYPES = {
    "Ada Derana": "news",
    "FM Derana": "news",
    "Ada Derana Sports": "sports",
    "Dream Star": "entertainment_music",
    "TV Derana": "entertainment",
}

HUMAN_REVIEW_COLUMNS = [
    "human_primary_signal",
    "human_secondary_signals",
    "human_actionable_content_demand",
    "human_requested_action",
    "human_requested_topic",
    "human_requested_format",
    "human_evidence_span",
    "human_language_or_script",
    "human_uncertainty_reason",
    "human_notes",
    "human_reviewer_id",
]


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _empty_count(series: pd.Series) -> int:
    normalized = series.astype("string").fillna("").str.strip()
    return int(normalized.eq("").sum())


def build_pilot_frame(
    comments_path: str | Path,
    videos_path: str | Path,
    preprocessed_path: str | Path | None = None,
) -> pd.DataFrame:
    """Assemble raw comments, existing preprocessing, and video context.

    The original source fields are retained. No rows are filtered and no
    human annotation columns are copied into this frame.
    """

    comments = load_comments(comments_path).copy()
    videos = load_videos(videos_path).copy()
    required = {"comment_id", "channel_id", "channel_name", "video_id", "comment_text"}
    missing = sorted(required.difference(comments.columns))
    if missing:
        raise ValueError(f"Pilot comments missing required columns: {missing}")

    if preprocessed_path and Path(preprocessed_path).exists():
        processed = pd.read_csv(preprocessed_path)
        processed_required = {"comment_id", "original_text", "cleaned_text"}
        if processed_required.issubset(processed.columns):
            text_columns = [
                "comment_id", "original_text", "cleaned_text", "has_sinhala", "has_latin",
                "mixed_sinhala_latin", "emoji_only", "char_length", "word_count",
                "review_reasons", "exclude_from_modeling", "repeated_cleaned_text",
            ]
            processed = processed[[column for column in text_columns if column in processed.columns]]
        else:
            processed = _preprocess_comments(comments)
    else:
        processed = _preprocess_comments(comments)

    frame = comments.merge(processed, on="comment_id", how="left", suffixes=("", "_processed"))
    frame["original_text"] = frame["original_text"].fillna(frame["comment_text"])
    frame["cleaned_text"] = frame["cleaned_text"].fillna(frame["original_text"])
    frame["script_category"] = frame.apply(_script_category, axis=1)

    video_columns = ["video_id", "title", "description", "channel_id", "channel_name"]
    video_context = videos[[column for column in video_columns if column in videos.columns]].copy()
    video_context = video_context.rename(columns={"title": "video_title", "description": "video_description"})
    frame = frame.merge(video_context, on="video_id", how="left", suffixes=("", "_video"))
    for column in ("video_title", "video_description"):
        if column not in frame:
            frame[column] = ""
        frame[column] = frame[column].fillna("")
    frame["video_url"] = "https://www.youtube.com/watch?v=" + frame["video_id"].astype(str)
    frame["parent_comment_text"] = ""
    frame["channel_type"] = frame["channel_name"].map(CHANNEL_TYPES).fillna("unknown")
    return frame


def build_sample_frame(sample_path: str | Path) -> pd.DataFrame:
    sample = pd.read_csv(sample_path).copy()
    required = {"comment_id", "channel_id", "channel_name", "video_id", "original_text", "cleaned_text"}
    missing = sorted(required.difference(sample.columns))
    if missing:
        raise ValueError(f"Annotation sample missing required columns: {missing}")
    sample["channel_type"] = sample["channel_name"].map(CHANNEL_TYPES).fillna("unknown")
    return sample


def _preprocess_comments(comments: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in comments.to_dict("records"):
        processed = preprocess_comment_text(row.get("comment_text", ""))
        processed["comment_id"] = row["comment_id"]
        rows.append(processed)
    return pd.DataFrame(rows)


def _script_category(row: pd.Series) -> str:
    if pd.notna(row.get("script_category")) and str(row.get("script_category")).strip():
        return str(row["script_category"])
    features = script_features(row.get("cleaned_text", row.get("comment_text", "")))
    if features["emoji_only"]:
        return "emoji_only"
    if features["mixed_sinhala_latin"]:
        return "mixed_sinhala_latin"
    if features["has_sinhala"]:
        return "sinhala_script"
    if features["has_latin"]:
        return "latin_script"
    return "other_or_symbolic"


def dataset_audit(frame: pd.DataFrame, source_name: str, source_path: str | Path | None = None) -> dict[str, Any]:
    """Return aggregate coverage only; no comment text is included."""

    context_columns = ["video_title", "video_description", "video_id", "channel_name", "original_text", "cleaned_text"]
    by_channel = []
    for (channel_name, channel_id), group in frame.groupby(["channel_name", "channel_id"], dropna=False):
        by_channel.append(
            {
                "channel_name": str(channel_name),
                "channel_id": str(channel_id),
                "comments": int(len(group)),
                "unique_videos": int(group["video_id"].nunique()),
                "script_categories": group["script_category"].value_counts().to_dict(),
                "candidate_rows": int(group.get("candidate_for_content_demand", pd.Series(False, index=group.index)).sum()),
            }
        )
    return {
        "source": source_name,
        "source_sha256": sha256(source_path) if source_path else None,
        "rows": int(len(frame)),
        "unique_comment_ids": int(frame["comment_id"].nunique()),
        "unique_channels": int(frame["channel_id"].nunique()),
        "unique_videos": int(frame["video_id"].nunique()),
        "channel_type_counts": frame["channel_type"].value_counts().to_dict(),
        "script_category_counts": frame["script_category"].value_counts().to_dict(),
        "missing_context": {column: _empty_count(frame[column]) for column in context_columns if column in frame},
        "by_channel": sorted(by_channel, key=lambda row: (row["channel_name"], row["channel_id"])),
    }


def prediction_summary(frame: pd.DataFrame) -> dict[str, Any]:
    by_channel = (
        frame.groupby(["channel_name", "channel_id"], dropna=False)
        .agg(comments=("comment_id", "size"), candidates=("candidate_for_content_demand", "sum"))
        .reset_index()
    )
    category = (
        frame.groupby(["channel_name", "primary_signal"], dropna=False)
        .size()
        .rename("count")
        .reset_index()
    )
    return {
        "candidate_count": int(frame["candidate_for_content_demand"].sum()),
        "candidate_rate": float(frame["candidate_for_content_demand"].mean()) if len(frame) else 0.0,
        "by_channel": by_channel.to_dict("records"),
        "by_category_and_channel": category.to_dict("records"),
    }


def write_json(payload: dict[str, Any], path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
