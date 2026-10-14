"""Video metadata preparation for future content-supply modelling."""

from __future__ import annotations

import ast
import json

import pandas as pd

from text_processing import clean_text


def parse_tags(value: object) -> list[str]:
    if value is None or pd.isna(value):
        return []
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "nan"}:
        return []
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(text)
            if isinstance(parsed, list):
                return [str(tag).strip() for tag in parsed if str(tag).strip()]
        except Exception:
            pass
    return [part.strip() for part in text.split(",") if part.strip()]


def prepare_video_metadata(videos: pd.DataFrame) -> pd.DataFrame:
    prepared = videos.copy()
    prepared["original_title"] = prepared["title"].fillna("").astype(str)
    prepared["cleaned_title"] = prepared["original_title"].map(clean_text)
    prepared["original_description"] = prepared["description"].fillna("").astype(str)
    prepared["cleaned_description"] = prepared["original_description"].map(clean_text)
    prepared["parsed_tags"] = prepared["tags"].map(parse_tags)
    prepared["published_at"] = pd.to_datetime(prepared["published_at"], utc=True, errors="coerce")
    return prepared[
        [
            "video_id",
            "channel_id",
            "channel_name",
            "original_title",
            "cleaned_title",
            "original_description",
            "cleaned_description",
            "tags",
            "parsed_tags",
            "published_at",
            "duration_seconds",
        ]
    ]
