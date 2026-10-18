"""Data Extraction Module for Component 4.

Connects to Supabase PostgreSQL, extracts channels, videos, and stats history,
and caches them locally as Parquet tables and DuckDB views for fast, reproducible analysis.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import duckdb
import pandas as pd

from shared.database.connection import connect
from shared.utils.paths import component_dir, get_data_paths

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def extract_portfolio_data(output_dir: Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Extract channels, videos, and video statistics from the research database."""
    target_dir = output_dir or component_dir(4)
    target_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Connecting to Supabase PostgreSQL...")
    conn = connect()

    try:
        # 1. Channels
        logger.info("Extracting research.channels...")
        channels_df = pd.read_sql_query(
            """
            SELECT channel_id, channel_name, subscriber_count, view_count,
                   video_count, description, published_at, collected_at
            FROM research.channels
            ORDER BY channel_name;
            """,
            conn,
        )
        channels_path = target_dir / "channels.parquet"
        channels_df.to_parquet(channels_path, index=False)
        logger.info("Saved %d channels to %s", len(channels_df), channels_path.name)

        # 2. Videos
        logger.info("Extracting research.videos...")
        videos_df = pd.read_sql_query(
            """
            SELECT video_id, channel_id, title, description, published_at,
                   tags, view_count, like_count, comment_count,
                   duration_seconds, collected_at
            FROM research.videos
            ORDER BY published_at ASC;
            """,
            conn,
        )
        videos_path = target_dir / "videos.parquet"
        videos_df.to_parquet(videos_path, index=False)
        logger.info("Saved %d videos to %s", len(videos_df), videos_path.name)

        # 3. Video Stats History
        logger.info("Extracting research.video_stats_history...")
        stats_df = pd.read_sql_query(
            """
            SELECT video_id, view_count, like_count, comment_count, collected_at
            FROM research.video_stats_history
            ORDER BY collected_at ASC;
            """,
            conn,
        )
        stats_path = target_dir / "video_stats.parquet"
        stats_df.to_parquet(stats_path, index=False)
        logger.info("Saved %d video stats history records to %s", len(stats_df), stats_path.name)

        # 4. Sync into local DuckDB database
        duckdb_path = get_data_paths().duckdb
        duckdb_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Syncing tables into DuckDB at %s...", duckdb_path)
        with duckdb.connect(str(duckdb_path)) as ddb:
            ddb.execute("CREATE SCHEMA IF NOT EXISTS component_4;")
            ddb.execute(f"CREATE OR REPLACE VIEW component_4.channels AS SELECT * FROM read_parquet('{channels_path.as_posix()}');")
            ddb.execute(f"CREATE OR REPLACE VIEW component_4.videos AS SELECT * FROM read_parquet('{videos_path.as_posix()}');")
            ddb.execute(f"CREATE OR REPLACE VIEW component_4.video_stats AS SELECT * FROM read_parquet('{stats_path.as_posix()}');")
        logger.info("DuckDB views created successfully.")

        return channels_df, videos_df, stats_df

    finally:
        conn.close()
        logger.info("Database connection closed.")


if __name__ == "__main__":
    extract_portfolio_data()
