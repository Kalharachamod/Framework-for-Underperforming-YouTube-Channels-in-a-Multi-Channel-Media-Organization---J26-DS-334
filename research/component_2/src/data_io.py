"""Dataset loading, validation, and reproducibility helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd


COMMENTS_REQUIRED_COLUMNS = {
    "comment_id",
    "channel_id",
    "channel_name",
    "video_id",
    "comment_text",
    "published_at",
    "edited_at",
    "like_count",
    "parent_comment_id",
}

VIDEOS_REQUIRED_COLUMNS = {
    "video_id",
    "channel_id",
    "channel_name",
    "title",
    "description",
    "tags",
    "published_at",
    "duration_seconds",
}


def load_comments(path: str | Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"comment_id": "string", "parent_comment_id": "string"})


def load_videos(path: str | Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"video_id": "string"})


def validate_required_columns(
    df: pd.DataFrame, required_columns: set[str], dataset_name: str
) -> list[str]:
    missing = sorted(required_columns.difference(df.columns))
    if missing:
        raise ValueError(f"{dataset_name} is missing required columns: {missing}")
    return sorted(required_columns)


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_datetime_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    parsed = df.copy()
    for column in columns:
        if column in parsed.columns:
            parsed[column] = pd.to_datetime(parsed[column], utc=True, errors="coerce")
    return parsed


def normalise_null_strings(series: pd.Series) -> pd.Series:
    return series.replace(
        {
            "null": pd.NA,
            "NULL": pd.NA,
            "None": pd.NA,
            "none": pd.NA,
            "nan": pd.NA,
            "NaN": pd.NA,
        }
    )
