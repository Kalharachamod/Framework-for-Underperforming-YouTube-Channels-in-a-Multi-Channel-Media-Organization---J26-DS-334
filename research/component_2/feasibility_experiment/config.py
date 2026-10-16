"""Configuration for the offline Component 2 feasibility experiment."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import DEFAULT_SEED


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PILOT_COMMENTS = PROJECT_ROOT / "data" / "raw" / "component_2" / "component2_pilot_comments.csv"
DEFAULT_PILOT_VIDEOS = PROJECT_ROOT / "data" / "raw" / "component_2" / "component2_pilot_videos.csv"
DEFAULT_PREPROCESSED = PROJECT_ROOT / "data" / "processed" / "component_2" / "preprocessed_comments.csv"
DEFAULT_ANNOTATION_SAMPLE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "component_2"
    / "annotation"
    / "component2_demand_annotation_sample.csv"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "component_2" / "feasibility_experiment"
DEFAULT_REPORT = Path(__file__).resolve().parent / "initial_feasibility_report.md"


@dataclass(frozen=True)
class ExperimentConfig:
    """Paths and deterministic sampling parameters for one experiment run."""

    pilot_comments: Path = DEFAULT_PILOT_COMMENTS
    pilot_videos: Path = DEFAULT_PILOT_VIDEOS
    preprocessed_comments: Path = DEFAULT_PREPROCESSED
    annotation_sample: Path = DEFAULT_ANNOTATION_SAMPLE
    output_dir: Path = DEFAULT_OUTPUT_DIR
    report_path: Path = DEFAULT_REPORT
    review_size: int = 100
    candidate_per_channel: int = 10
    control_per_channel: int = 10
    seed: int = DEFAULT_SEED
