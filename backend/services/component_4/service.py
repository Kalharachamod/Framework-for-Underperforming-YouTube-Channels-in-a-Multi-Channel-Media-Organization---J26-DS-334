"""Component 4 Research Data Service.

Provides clean read-only access to Component 4 artifacts:
- Emerging topic signals
- Hierarchical topic trajectories
- Comparative benchmark evaluation
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
from shared.utils.paths import component_dir

logger = logging.getLogger(__name__)


class Component4Service:
    """Read-only access to Component 4 stored research artifacts."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or component_dir(4)

    @property
    def signals_path(self) -> Path:
        return self.data_dir / "emerging_signals.parquet"

    @property
    def benchmark_path(self) -> Path:
        return self.data_dir / "benchmark_evaluation.parquet"

    @property
    def trajectories_path(self) -> Path:
        return self.data_dir / "channel_topic_weekly.parquet"

    @property
    def videos_path(self) -> Path:
        return self.data_dir / "preprocessed_videos.parquet"

    def get_status(self) -> dict[str, Any]:
        """Return existence and record counts of Component 4 artifacts."""
        return {
            "has_videos": self.videos_path.exists(),
            "has_trajectories": self.trajectories_path.exists(),
            "has_emerging_signals": self.signals_path.exists(),
            "has_benchmarks": self.benchmark_path.exists(),
            "total_signals_detected": len(pd.read_parquet(self.signals_path)) if self.signals_path.exists() else 0,
        }

    def get_emerging_topics(
        self,
        channel_id: str | None = None,
        niche: str | None = None,
        min_score: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Retrieve detected emerging topic signals with filtering."""
        if not self.signals_path.exists():
            return []

        df = pd.read_parquet(self.signals_path)
        if df.empty:
            return []

        if channel_id:
            df = df[df["channel_id"] == channel_id]
        if niche:
            df = df[df["channel_niche"].str.lower() == niche.lower()]
        if min_score > 0:
            df = df[df["signal_score"] >= min_score]

        return df.to_dict(orient="records")

    def get_benchmarks(self) -> list[dict[str, Any]]:
        """Retrieve comparative baseline evaluation results."""
        if not self.benchmark_path.exists():
            return []
        df = pd.read_parquet(self.benchmark_path)
        return df.to_dict(orient="records")

    def get_topic_trajectories(self, channel_id: str | None = None, topic_id: int | None = None) -> list[dict[str, Any]]:
        """Retrieve weekly dynamic prevalence trajectories."""
        if not self.trajectories_path.exists():
            return []
        df = pd.read_parquet(self.trajectories_path)
        if channel_id:
            df = df[df["channel_id"] == channel_id]
        if topic_id is not None:
            df = df[df["topic_id"] == topic_id]
        return df.to_dict(orient="records")
