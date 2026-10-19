"""Main Preprocessing Pipeline Runner for Component 4.

Runs the complete data preparation workflow:
1. Data Extraction from Supabase PostgreSQL
2. Multilingual text normalization (Sinhala / English / Tanglish)
3. Content-format and weekly temporal aggregation features
4. Quality checks and final Parquet persistence for BERTopic modeling
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

from research.component_4.preprocessing.extract_data import extract_portfolio_data
from research.component_4.preprocessing.format_features import extract_format_features
from research.component_4.preprocessing.text_cleaner import construct_video_document
from shared.utils.paths import component_dir

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def run_preprocessing_pipeline(force_extract: bool = False) -> pd.DataFrame:
    """Execute the full Component 4 data extraction and preprocessing pipeline."""
    target_dir = component_dir(4)
    target_dir.mkdir(parents=True, exist_ok=True)
    output_parquet = target_dir / "preprocessed_videos.parquet"

    # Step 1: Extract or load cached raw data
    raw_videos_path = target_dir / "videos.parquet"
    channels_path = target_dir / "channels.parquet"

    if force_extract or not raw_videos_path.exists():
        logger.info("[Step 1/4] Extracting fresh dataset from Supabase PostgreSQL...")
        channels_df, videos_df, _ = extract_portfolio_data(target_dir)
    else:
        logger.info("[Step 1/4] Loading cached raw dataset from %s...", raw_videos_path)
        videos_df = pd.read_parquet(raw_videos_path)
        channels_df = pd.read_parquet(channels_path) if channels_path.exists() else pd.DataFrame()

    logger.info("Loaded %d raw video records.", len(videos_df))

    # Step 2: Merge channel names if available
    if not channels_df.empty and "channel_name" in channels_df.columns:
        ch_map = channels_df.set_index("channel_id")["channel_name"].to_dict()
        videos_df["channel_name"] = videos_df["channel_id"].map(ch_map).fillna("Unknown Channel")
    else:
        videos_df["channel_name"] = "Unknown Channel"

    # Step 3: Text Cleaning & Semantic Document Construction
    logger.info("[Step 2/4] Cleaning multilingual text and constructing documents...")
    documents = []
    languages = []

    for _, row in videos_df.iterrows():
        doc, lang = construct_video_document(
            title=row.get("title"),
            description=row.get("description"),
            tags=row.get("tags"),
            title_weight=2,  # Boost title importance
        )
        documents.append(doc)
        languages.append(lang)

    videos_df["clean_document"] = documents
    videos_df["language_profile"] = languages

    # Step 4: Content-Format, Niche & Temporal Features
    logger.info("[Step 3/4] Extracting format features, duration bands, and weekly bins...")
    enriched_df = extract_format_features(videos_df)

    # Step 5: Data Quality Filtering & Verification
    logger.info("[Step 4/4] Validating dataset quality...")
    # Drop rows with empty document
    valid_mask = enriched_df["clean_document"].str.strip().str.len() > 3
    final_df = enriched_df[valid_mask].copy()

    # Save to final processed Parquet
    final_df.to_parquet(output_parquet, index=False)
    logger.info("Successfully saved %d clean preprocessed videos to %s", len(final_df), output_parquet)

    # Summary Statistics
    logger.info("=== PREPROCESSING AUDIT SUMMARY ===")
    logger.info("Total Videos Processed: %d", len(final_df))
    logger.info("Unique Channels: %d", final_df["channel_id"].nunique())
    logger.info("Date Range: %s to %s", final_df["published_at"].min(), final_df["published_at"].max())
    logger.info("Unique Weekly Bins: %d", final_df["upload_week"].nunique())

    logger.info("\nLanguage Distribution:\n%s", final_df["language_profile"].value_counts().to_string())
    logger.info("\nContent Format Distribution:\n%s", final_df["duration_band"].value_counts().to_string())
    logger.info("\nChannel Niche Distribution:\n%s", final_df["channel_niche"].value_counts().to_string())

    return final_df


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    run_preprocessing_pipeline(force_extract=True)
