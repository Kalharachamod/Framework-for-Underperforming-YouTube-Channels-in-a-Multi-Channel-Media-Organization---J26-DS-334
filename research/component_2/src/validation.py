"""Validation and relationship checks for the Component 2 pilot datasets."""

from __future__ import annotations

import pandas as pd


def duplicate_count(df: pd.DataFrame, column: str) -> int:
    return int(df[column].duplicated().sum())


def duplicate_value_summary(df: pd.DataFrame, column: str, limit: int = 10) -> pd.DataFrame:
    counts = df[column].fillna("").value_counts()
    repeated = counts[counts > 1].head(limit)
    return repeated.rename_axis(column).reset_index(name="count")


def missing_value_summary(df: pd.DataFrame) -> pd.DataFrame:
    rows = len(df)
    summary = pd.DataFrame(
        {
            "missing_count": df.isna().sum(),
            "missing_percent": (df.isna().sum() / rows * 100 if rows else 0).round(2),
        }
    )
    return summary.reset_index().rename(columns={"index": "column"})


def comments_per_channel(comments: pd.DataFrame) -> pd.DataFrame:
    return (
        comments.groupby(["channel_id", "channel_name"], dropna=False)
        .agg(total_comments=("comment_id", "count"), videos_with_comments=("video_id", "nunique"))
        .reset_index()
        .sort_values("total_comments", ascending=False)
    )


def comments_per_video(comments: pd.DataFrame) -> pd.DataFrame:
    return (
        comments.groupby(["channel_id", "video_id"], dropna=False)
        .agg(total_comments=("comment_id", "count"))
        .reset_index()
        .sort_values("total_comments", ascending=False)
    )


def video_channel_distribution(videos: pd.DataFrame) -> pd.DataFrame:
    return (
        videos.groupby(["channel_id", "channel_name"], dropna=False)
        .agg(total_videos=("video_id", "nunique"))
        .reset_index()
        .sort_values("total_videos", ascending=False)
    )


def video_match_summary(comments: pd.DataFrame, videos: pd.DataFrame) -> dict[str, int]:
    commented_video_ids = set(comments["video_id"].dropna().astype(str))
    stored_video_ids = set(videos["video_id"].dropna().astype(str))
    matched = commented_video_ids.intersection(stored_video_ids)
    return {
        "commented_videos": len(commented_video_ids),
        "matched_videos": len(matched),
        "missing_video_metadata": len(commented_video_ids - stored_video_ids),
        "unused_stored_videos": len(stored_video_ids - commented_video_ids),
    }


def channel_relationship_mismatches(comments: pd.DataFrame, videos: pd.DataFrame) -> pd.DataFrame:
    joined = comments[["comment_id", "video_id", "channel_id"]].merge(
        videos[["video_id", "channel_id"]].rename(columns={"channel_id": "video_channel_id"}),
        on="video_id",
        how="left",
    )
    return joined[
        joined["video_channel_id"].notna()
        & (joined["channel_id"].astype(str) != joined["video_channel_id"].astype(str))
    ]


def reply_summary(comments: pd.DataFrame) -> pd.DataFrame:
    is_reply = comments["parent_comment_id"].notna() & (comments["parent_comment_id"].astype(str).str.strip() != "")
    return pd.DataFrame(
        {
            "comment_type": ["top_level", "reply"],
            "count": [int((~is_reply).sum()), int(is_reply.sum())],
        }
    )


def date_range(df: pd.DataFrame, column: str) -> dict[str, object]:
    values = pd.to_datetime(df[column], utc=True, errors="coerce")
    return {
        "min": values.min(),
        "max": values.max(),
        "missing": int(values.isna().sum()),
    }


def text_length_stats(comments: pd.DataFrame, text_column: str = "comment_text") -> pd.Series:
    lengths = comments[text_column].fillna("").astype(str).str.len()
    return lengths.describe()
