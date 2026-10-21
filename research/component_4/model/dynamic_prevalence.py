"""Dynamic Topic Prevalence Modeling for Component 4.

Aggregates video topic assignments into weekly channel-topic-time trajectories:
p_{c, k, t} = N_{c, k, t} / N_{c, t}
Extracts temporal dynamics, format prevalence (Shorts vs Long-form), and flags sparse observations.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from research.component_4.model.topic_model import TopicModel
from shared.utils.paths import component_dir

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def build_channel_topic_trajectories(
    videos_df: pd.DataFrame,
    topic_model: TopicModel,
    save_parquet: bool = True,
) -> pd.DataFrame:
    """Construct weekly channel-topic prevalence trajectories p_{c, k, t}.

    Args:
        videos_df: Preprocessed videos DataFrame with clean_document, published_at, upload_week.
        topic_model: Fitted TopicModel instance.
        save_parquet: If True, saves to data/processed/component_4/channel_topic_weekly.parquet.

    Returns:
        DataFrame of channel-topic-time observations.
    """
    logger.info("Inferring topic assignments for %d videos...", len(videos_df))
    topic_ids, probs = topic_model.transform(videos_df["clean_document"].tolist())

    df = videos_df.copy()
    df["assigned_topic_id"] = topic_ids
    df["topic_probability"] = probs
    df["topic_label"] = df["assigned_topic_id"].map(topic_model.topic_labels_)

    # 1. Total weekly uploads per channel: N_{c, t}
    weekly_channel_totals = (
        df.groupby(["channel_id", "upload_week"])
        .size()
        .reset_index(name="channel_weekly_total_uploads")
    )

    # 2. Topic counts & format metrics per channel-topic-week: N_{c, k, t}
    grouped = df.groupby(["channel_id", "channel_name", "channel_niche", "assigned_topic_id", "topic_label", "upload_week"])

    records = []
    for (ch_id, ch_name, niche, topic_id, topic_label, week), group in grouped:
        n_videos = len(group)
        n_shorts = int(group["is_short"].sum())
        avg_eng = float(group["engagement_rate"].mean())
        avg_likes_1k = float(group["likes_per_1k_views"].mean())
        avg_prob = float(group["topic_probability"].mean())

        records.append({
            "channel_id": ch_id,
            "channel_name": ch_name,
            "channel_niche": niche,
            "topic_id": topic_id,
            "topic_label": topic_label,
            "upload_week": week,
            "video_count": n_videos,
            "shorts_count": n_shorts,
            "shorts_ratio": round(n_shorts / n_videos, 3) if n_videos > 0 else 0.0,
            "mean_topic_probability": round(avg_prob, 4),
            "mean_engagement_rate": round(avg_eng, 3),
            "mean_likes_per_1k": round(avg_likes_1k, 2),
        })

    topic_weekly_df = pd.DataFrame(records)

    # Merge weekly channel total uploads to calculate normalized prevalence p_{c, k, t}
    merged_df = topic_weekly_df.merge(
        weekly_channel_totals,
        on=["channel_id", "upload_week"],
        how="left",
    )

    # Normalized prevalence p_{c, k, t} = N_{c, k, t} / N_{c, t}
    merged_df["topic_prevalence"] = (
        merged_df["video_count"] / merged_df["channel_weekly_total_uploads"]
    ).round(4)

    # Sparse observation flag: channel had <= 2 uploads in that week
    merged_df["is_sparse_channel_week"] = merged_df["channel_weekly_total_uploads"] <= 2

    # Sort chronologically by channel, topic, and week
    merged_df = merged_df.sort_values(by=["channel_id", "topic_id", "upload_week"]).reset_index(drop=True)

    if save_parquet:
        out_path = component_dir(4) / "channel_topic_weekly.parquet"
        merged_df.to_parquet(out_path, index=False)
        logger.info("Saved %d channel-topic-time observations to %s", len(merged_df), out_path)

    return merged_df


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    target_dir = component_dir(4)
    videos_file = target_dir / "preprocessed_videos.parquet"

    if not videos_file.exists():
        logger.error("preprocessed_videos.parquet not found. Run run_preprocessing.py first.")
        sys.exit(1)

    v_df = pd.read_parquet(videos_file)

    # Train topic model
    t_model = TopicModel(n_topics=15)
    t_model.fit(v_df["clean_document"].tolist())

    # Build trajectories
    trajectories_df = build_channel_topic_trajectories(v_df, t_model)

    print("\nSample Weekly Topic Prevalence Trajectories:")
    sample = trajectories_df[[
        "channel_name", "topic_label", "upload_week", "video_count",
        "channel_weekly_total_uploads", "topic_prevalence", "shorts_ratio"
    ]].head(15)
    print(sample.to_string(index=False))
