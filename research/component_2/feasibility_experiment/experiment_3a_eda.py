"""Experiment 3A EDA: validation and exploratory analysis of the full expanded corpus.

Applies the same validation (`src/validation.py`) and EDA (`src/eda.py`)
helpers used for the 2,000-comment pilot (notebooks 01 and 02) to the full
84,002-comment Derana corpus, and writes a pilot-versus-full comparison.
Outputs are aggregate tables and charts only, written to the Git-ignored
`data/analysis/component_2/02_full_corpus_84002_comments/` directory
(the pilot outputs are in `01_pilot_2000_comments/`).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parents[2]
SRC_DIR = REPO_ROOT / "research" / "component_2" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))  # the pilot helpers use notebook-style imports

import eda  # noqa: E402
import validation  # noqa: E402

CORPUS_DIR = PACKAGE_DIR / "outputs" / "experiment_3a"
PILOT_COMMENTS = REPO_ROOT / "data" / "raw" / "component_2" / "component2_pilot_comments.csv"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "analysis" / "component_2" / "02_full_corpus_84002_comments"


def _iso_dates(series: pd.Series) -> pd.Series:
    """Standardise mixed pilot/API timestamp formats before the pilot helpers parse them."""

    return pd.to_datetime(series, utc=True, errors="coerce", format="ISO8601").dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def load_full_corpus(corpus_dir: Path = CORPUS_DIR) -> tuple[pd.DataFrame, pd.DataFrame]:
    comments = pd.read_csv(corpus_dir / "expanded_comments.csv", dtype=str, keep_default_na=False)
    comments = comments.rename(columns={"raw_comment_text": "comment_text"})
    comments["parent_comment_id"] = comments["parent_comment_id"].replace("", pd.NA)
    comments["published_at"] = _iso_dates(comments["published_at"])
    videos = pd.read_csv(corpus_dir / "expanded_videos.csv", dtype=str, keep_default_na=False)
    videos["published_at"] = _iso_dates(videos["published_at"])
    return comments, videos


def profile(comments: pd.DataFrame) -> dict[str, float]:
    features = eda.add_text_features(comments[["comment_id", "comment_text"]])
    per_video = eda.comments_per_video_summary(comments)
    replies = validation.reply_summary(comments).set_index("comment_type")["count"]
    return {
        "comments": int(len(comments)),
        "channels": int(comments["channel_name"].nunique()),
        "videos_with_comments": int(comments["video_id"].nunique()),
        "duplicate_comment_ids": validation.duplicate_count(comments, "comment_id"),
        "empty_comments": int(comments["comment_text"].fillna("").str.strip().eq("").sum()),
        "replies_share_pct": round(100 * replies["reply"] / len(comments), 1),
        "median_comments_per_video": float(per_video["50%"]),
        "median_characters": float(features["char_length"].median()),
        "median_words": float(features["word_count"].median()),
        "sinhala_script_pct": round(100 * features["has_sinhala"].mean(), 1),
        "latin_script_pct": round(100 * features["has_latin"].mean(), 1),
        "mixed_script_pct": round(100 * features["mixed_sinhala_latin"].mean(), 1),
        "emoji_only_pct": round(100 * features["emoji_only"].mean(), 1),
        "very_short_under_5_chars_pct": round(100 * (features["char_length"] < 5).mean(), 1),
        "repeated_character_pattern_pct": round(100 * features["has_repeated_char_pattern"].mean(), 1),
    }


def run(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    charts = output_dir / "charts"
    comments, videos = load_full_corpus()
    features = eda.add_text_features(comments[["comment_id", "comment_text"]])

    # Validation (notebook 01 equivalents)
    validation.missing_value_summary(comments[["comment_id", "video_id", "channel_id", "comment_text", "published_at"]]).to_csv(
        output_dir / "missing_values.csv", index=False
    )
    per_channel = validation.comments_per_channel(comments)
    per_channel.to_csv(output_dir / "comments_per_channel.csv", index=False)
    video_dist = validation.video_channel_distribution(videos)
    video_dist.to_csv(output_dir / "videos_per_channel.csv", index=False)
    mismatches = validation.channel_relationship_mismatches(comments, videos)
    validation_summary = {
        "duplicate_comment_ids": validation.duplicate_count(comments, "comment_id"),
        "duplicate_video_ids": validation.duplicate_count(videos, "video_id"),
        "video_match": validation.video_match_summary(comments, videos),
        "comment_channel_mismatches": int(len(mismatches)),
        "comment_dates": {k: str(v) for k, v in validation.date_range(comments, "published_at").items()},
        "video_dates": {k: str(v) for k, v in validation.date_range(videos, "published_at").items()},
        "text_length": {k: round(float(v), 1) for k, v in validation.text_length_stats(comments).items()},
        "replies": validation.reply_summary(comments).set_index("comment_type")["count"].to_dict(),
    }

    # EDA (notebook 02 equivalents)
    eda.potential_spam_summary(features.assign(comment_text=comments["comment_text"])).to_csv(
        output_dir / "spam_like_summary.csv", index=False
    )
    timeline = eda.publication_timeline(comments, "published_at")
    timeline.to_csv(output_dir / "comment_timeline_monthly.csv", index=False)
    per_video_counts = validation.comments_per_video(comments)["total_comments"]
    script_shares = pd.Series(
        {
            "Sinhala script": features["has_sinhala"].mean() * 100,
            "Latin script": features["has_latin"].mean() * 100,
            "Mixed Sinhala-Latin": features["mixed_sinhala_latin"].mean() * 100,
            "Emoji only": features["emoji_only"].mean() * 100,
        }
    )
    eda.save_bar_chart(per_channel.set_index("channel_name")["total_comments"], "Comments per channel (full corpus)", "Comments", charts / "eda_comments_per_channel.png")
    eda.save_bar_chart(video_dist.set_index("channel_name")["total_videos"], "Videos per channel (full corpus)", "Videos", charts / "eda_videos_per_channel.png")
    eda.save_histogram(per_video_counts.clip(upper=400), "Comments per video (capped at 400)", "Comments per video", charts / "eda_comments_per_video_histogram.png", bins=40)
    eda.save_histogram(features["char_length"].clip(upper=400), "Comment length (characters, capped at 400)", "Characters", charts / "eda_character_length_histogram.png", bins=40)
    eda.save_histogram(features["word_count"].clip(upper=80), "Comment length (words, capped at 80)", "Words", charts / "eda_word_count_histogram.png", bins=40)
    eda.save_bar_chart(script_shares.round(1), "Script features (% of comments; overlapping)", "% of comments", charts / "eda_script_features.png")
    eda.save_bar_chart(timeline.set_index("period")["count"], "Comments per month (full corpus)", "Comments", charts / "eda_comments_per_month.png")

    # Pilot versus full corpus
    pilot = pd.read_csv(PILOT_COMMENTS, dtype=str, keep_default_na=False)
    pilot["parent_comment_id"] = pilot["parent_comment_id"].str.strip().replace({"": pd.NA, "null": pd.NA, "None": pd.NA})
    comparison = pd.DataFrame({"pilot_2000": profile(pilot), "full_corpus": profile(comments)})
    comparison.to_csv(output_dir / "pilot_vs_full_corpus.csv")

    summary = {"validation": validation_summary, "comparison": comparison.to_dict()}
    (output_dir / "full_corpus_eda_summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    summary = run()
    print(json.dumps(summary["validation"], indent=2, default=str))
    print(pd.DataFrame(summary["comparison"]).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
