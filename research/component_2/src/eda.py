"""Reusable exploratory analysis helpers for Component 2."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from text_processing import script_features


def add_text_features(comments: pd.DataFrame, text_column: str = "comment_text") -> pd.DataFrame:
    feature_df = pd.DataFrame([script_features(text) for text in comments[text_column]], index=comments.index)
    return pd.concat([comments.reset_index(drop=True), feature_df.reset_index(drop=True)], axis=1)


def comments_per_video_summary(comments: pd.DataFrame) -> pd.Series:
    return comments.groupby("video_id")["comment_id"].count().describe()


def publication_timeline(df: pd.DataFrame, date_column: str, freq: str = "M") -> pd.DataFrame:
    dates = pd.to_datetime(df[date_column], utc=True, errors="coerce").dropna()
    return dates.dt.to_period(freq).value_counts().sort_index().rename_axis("period").reset_index(name="count")


def potential_spam_summary(comments_with_features: pd.DataFrame) -> pd.DataFrame:
    text_counts = comments_with_features["comment_text"].fillna("").astype(str).value_counts()
    repeated_texts = int((text_counts > 1).sum())
    return pd.DataFrame(
        {
            "metric": [
                "emoji_only",
                "very_short_under_5_chars",
                "repeated_comment_text_values",
                "repeated_character_patterns",
            ],
            "value": [
                int(comments_with_features["emoji_only"].sum()),
                int((comments_with_features["char_length"] < 5).sum()),
                repeated_texts,
                int(comments_with_features["has_repeated_char_pattern"].sum()),
            ],
        }
    )


def save_bar_chart(series: pd.Series, title: str, ylabel: str, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 5))
    series.plot(kind="bar", ax=ax)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xlabel("")
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def save_histogram(values: pd.Series, title: str, xlabel: str, output_path: str | Path, bins: int = 30) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 5))
    values.dropna().plot(kind="hist", bins=bins, ax=ax)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path
