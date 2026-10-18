"""Prepare a calibration-excluded, video-grouped Component 2 sampling frame.

Experiment 2A.2 corrects the leakage and data-attrition problem identified by
Experiment 2A.1. It preserves every historical input and output, treats the
existing 500-comment sample as exploratory, and creates new local-only review
artifacts without assigning human labels.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from research.component_2.src.data_io import load_videos

from .annotation_schema import validate_annotation_frame
from .audit import sha256
from .config import DEFAULT_PILOT_COMMENTS, DEFAULT_PILOT_VIDEOS, DEFAULT_PREPROCESSED
from .partition_guard import PartitionGuard, load_partition_lock
from .prepare_experiment_2a import (
    ACTIONABILITY_LABELS,
    PRIMARY_SIGNALS,
    REVIEW_ANNOTATION_FIELDS,
    build_demand_enriched_pool,
    build_experiment_source,
    create_blank_review_template,
)


EXPERIMENT_2A2_SEED = 20261018
HELD_OUT_VIDEO_FRACTION = 0.20
TEMPORAL_STRATA = 4
PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_CALIBRATION = PACKAGE_DIR / "outputs" / "calibration_40_comments.csv"
DEFAULT_EXPLORATORY_SAMPLE = (
    PACKAGE_DIR / "outputs" / "experiment_2a" / "representative_evaluation_500.csv"
)
DEFAULT_OUTPUT_DIR = PACKAGE_DIR / "outputs" / "experiment_2a2"


def _stable_hash(value: object, seed: int, namespace: str) -> str:
    payload = f"{seed}:{namespace}:{value}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def load_calibration_frame(path: str | Path = DEFAULT_CALIBRATION) -> pd.DataFrame:
    """Load the frozen calibration rows needed only to identify seen videos."""

    calibration_path = Path(path)
    if not calibration_path.exists():
        raise FileNotFoundError(
            "The frozen 40-comment calibration file is required to exclude its videos: "
            f"{calibration_path}"
        )
    calibration = pd.read_csv(calibration_path, dtype={"comment_id": "string"})
    required = {
        "comment_id",
        "human_primary_signal",
        "human_actionable_content_demand",
    }
    missing = sorted(required.difference(calibration.columns))
    if missing:
        raise ValueError(f"Calibration file is missing required columns: {missing}")
    if len(calibration) != 40 or calibration["comment_id"].nunique() != 40:
        raise ValueError(
            "Expected the frozen calibration file to contain exactly 40 unique comments"
        )
    for column in ("human_primary_signal", "human_actionable_content_demand"):
        if calibration[column].fillna("").astype(str).str.strip().eq("").any():
            raise ValueError(f"Calibration file has incomplete reviewed values in {column}")
    invalid_signals = sorted(set(calibration["human_primary_signal"]) - set(PRIMARY_SIGNALS))
    invalid_actionability = sorted(
        set(calibration["human_actionable_content_demand"]) - set(ACTIONABILITY_LABELS)
    )
    if invalid_signals:
        raise ValueError(f"Calibration contains invalid primary signals: {invalid_signals}")
    if invalid_actionability:
        raise ValueError(
            f"Calibration contains invalid actionability labels: {invalid_actionability}"
        )
    return calibration


def calibration_video_ids(
    source: pd.DataFrame,
    calibration: pd.DataFrame,
) -> set[str]:
    """Resolve calibration comments to source video IDs without copying labels."""

    source_ids = set(source["comment_id"].astype(str))
    calibration_ids = set(calibration["comment_id"].astype(str))
    missing = sorted(calibration_ids.difference(source_ids))
    if missing:
        raise ValueError(
            f"Calibration contains {len(missing)} comment IDs absent from the pilot source"
        )
    matched = source[source["comment_id"].astype(str).isin(calibration_ids)]
    return set(matched["video_id"].astype(str))


def build_video_sampling_frame(
    source: pd.DataFrame,
    calibration: pd.DataFrame,
    videos_path: str | Path = DEFAULT_PILOT_VIDEOS,
) -> pd.DataFrame:
    """Create one provenance row per comment-covered video."""

    videos = load_videos(videos_path).copy()
    required = {"video_id", "published_at"}
    missing = sorted(required.difference(videos.columns))
    if missing:
        raise ValueError(f"Pilot videos are missing required columns: {missing}")

    covered = (
        source.groupby(["video_id", "channel_id", "channel_name"], as_index=False)
        .agg(comment_count=("comment_id", "size"))
    )
    video_dates = videos[["video_id", "published_at"]].drop_duplicates("video_id").rename(
        columns={"published_at": "video_published_at"}
    )
    frame = covered.merge(video_dates, on="video_id", how="left", validate="one_to_one")
    frame["video_id"] = frame["video_id"].astype(str)
    frame["video_published_at"] = pd.to_datetime(
        frame["video_published_at"], utc=True, errors="coerce"
    )
    if frame["video_published_at"].isna().any():
        missing_dates = int(frame["video_published_at"].isna().sum())
        raise ValueError(
            f"Cannot create temporal sampling strata: {missing_dates} covered videos lack dates"
        )

    calibration_ids = set(calibration["comment_id"].astype(str))
    calibration_videos = calibration_video_ids(source, calibration)
    calibration_counts = (
        source[source["comment_id"].astype(str).isin(calibration_ids)]
        .groupby("video_id")["comment_id"]
        .size()
        .to_dict()
    )
    frame["calibration_comment_count"] = (
        frame["video_id"].map(calibration_counts).fillna(0).astype(int)
    )
    frame["calibration_video_excluded"] = frame["video_id"].isin(calibration_videos)
    return frame.sort_values(["channel_name", "video_published_at", "video_id"]).reset_index(
        drop=True
    )


def _assign_temporal_strata(frame: pd.DataFrame, strata: int) -> pd.DataFrame:
    if strata < 1:
        raise ValueError("Temporal strata must be at least 1")
    parts: list[pd.DataFrame] = []
    for _, channel_frame in frame.groupby("channel_name", sort=True):
        ordered = channel_frame.sort_values(
            ["video_published_at", "video_id"], kind="mergesort"
        ).reset_index(drop=True)
        size = len(ordered)
        ordered["temporal_stratum"] = [
            min(strata, (position * strata) // size + 1) for position in range(size)
        ]
        parts.append(ordered)
    return pd.concat(parts, ignore_index=True)


def create_video_partition_manifest(
    source: pd.DataFrame,
    calibration: pd.DataFrame,
    *,
    videos_path: str | Path = DEFAULT_PILOT_VIDEOS,
    seed: int = EXPERIMENT_2A2_SEED,
    held_out_fraction: float = HELD_OUT_VIDEO_FRACTION,
    temporal_strata: int = TEMPORAL_STRATA,
) -> pd.DataFrame:
    """Assign whole videos to calibration, held-out, or development roles.

    Eligible videos are sampled without replacement within channel and
    within-channel chronological strata. Selection uses only video provenance,
    never comment text, heuristic predictions, or human labels.
    """

    if not 0 < held_out_fraction < 1:
        raise ValueError("held_out_fraction must be between 0 and 1")
    frame = build_video_sampling_frame(source, calibration, videos_path)
    excluded = frame[frame["calibration_video_excluded"]].copy()
    eligible = frame[~frame["calibration_video_excluded"]].copy()
    eligible = _assign_temporal_strata(eligible, temporal_strata)

    selected_video_ids: set[str] = set()
    stratum_metadata: dict[tuple[str, int], tuple[int, int]] = {}
    for (channel, time_block), stratum in eligible.groupby(
        ["channel_name", "temporal_stratum"], sort=True
    ):
        population = len(stratum)
        if population == 1:
            selected = 0
        else:
            selected = max(1, int(math.floor(population * held_out_fraction + 0.5)))
            selected = min(selected, population - 1)
        namespace = f"held-out:{channel}:{time_block}"
        ranked = stratum.assign(
            _selection_hash=stratum["video_id"].map(
                lambda value: _stable_hash(value, seed, namespace)
            )
        ).sort_values(["_selection_hash", "video_id"], kind="mergesort")
        selected_video_ids.update(ranked.head(selected)["video_id"].astype(str))
        stratum_metadata[(str(channel), int(time_block))] = (population, selected)

    eligible["dataset_role"] = "development_pool"
    eligible.loc[
        eligible["video_id"].isin(selected_video_ids), "dataset_role"
    ] = "held_out_evaluation"
    eligible["stratum_video_count"] = eligible.apply(
        lambda row: stratum_metadata[(str(row["channel_name"]), int(row["temporal_stratum"]))][0],
        axis=1,
    )
    eligible["selected_video_count"] = eligible.apply(
        lambda row: stratum_metadata[(str(row["channel_name"]), int(row["temporal_stratum"]))][1],
        axis=1,
    )
    eligible["video_selection_probability"] = (
        eligible["selected_video_count"] / eligible["stratum_video_count"]
    )
    eligible["sampling_weight"] = eligible["video_selection_probability"].map(
        lambda value: 1.0 / value if value > 0 else pd.NA
    )

    eligible["temporal_stratum"] = eligible["temporal_stratum"].astype("Int64")
    eligible["stratum_video_count"] = eligible["stratum_video_count"].astype("Int64")
    eligible["selected_video_count"] = eligible["selected_video_count"].astype("Int64")

    excluded["temporal_stratum"] = pd.Series(pd.NA, index=excluded.index, dtype="Int64")
    excluded["dataset_role"] = "calibration_only"
    excluded["stratum_video_count"] = pd.Series(pd.NA, index=excluded.index, dtype="Int64")
    excluded["selected_video_count"] = pd.Series(pd.NA, index=excluded.index, dtype="Int64")
    excluded["video_selection_probability"] = 0.0
    excluded["sampling_weight"] = float("nan")

    manifest = pd.concat([eligible, excluded], ignore_index=True)
    manifest["split_seed"] = seed
    manifest["held_out_video_fraction_target"] = held_out_fraction
    manifest["selection_method"] = (
        "stable-hash simple random sample of videos within channel and chronological stratum"
    )
    manifest.loc[
        manifest["dataset_role"].eq("calibration_only"), "selection_method"
    ] = "excluded because a calibration comment from this video informed earlier analysis"
    columns = [
        "video_id",
        "channel_id",
        "channel_name",
        "video_published_at",
        "comment_count",
        "temporal_stratum",
        "dataset_role",
        "calibration_video_excluded",
        "calibration_comment_count",
        "split_seed",
        "held_out_video_fraction_target",
        "stratum_video_count",
        "selected_video_count",
        "video_selection_probability",
        "sampling_weight",
        "selection_method",
    ]
    return manifest[columns].sort_values(
        ["dataset_role", "channel_name", "video_published_at", "video_id"],
        kind="mergesort",
    ).reset_index(drop=True)


def attach_video_partitions(source: pd.DataFrame, manifest: pd.DataFrame) -> pd.DataFrame:
    """Attach one and only one video-level role to every source comment."""

    partition_columns = [
        "video_id",
        "dataset_role",
        "temporal_stratum",
        "video_published_at",
        "video_selection_probability",
        "sampling_weight",
    ]
    if manifest["video_id"].duplicated().any():
        raise ValueError("Video partition manifest contains duplicate video IDs")
    result = source.merge(
        manifest[partition_columns], on="video_id", how="left", validate="many_to_one"
    )
    if result["dataset_role"].isna().any():
        raise ValueError("At least one source comment has no video partition")
    return result


def _order_for_review(frame: pd.DataFrame, seed: int, namespace: str) -> pd.DataFrame:
    ordered = frame.copy()
    ordered["_review_hash"] = ordered["comment_id"].map(
        lambda value: _stable_hash(value, seed, namespace)
    )
    ordered = ordered.sort_values(["_review_hash", "comment_id"], kind="mergesort")
    ordered = ordered.drop(columns="_review_hash").reset_index(drop=True)
    ordered["review_order"] = range(1, len(ordered) + 1)
    return ordered


def select_matched_controls(
    screened_development: pd.DataFrame,
    candidates: pd.DataFrame,
    *,
    seed: int = EXPERIMENT_2A2_SEED,
) -> pd.DataFrame:
    """Select one blinded control for each enriched candidate.

    Exact matching uses channel, script category, and temporal stratum. Fallback
    levels are explicit in the local selection manifest and never appear in the
    reviewer-facing CSV.
    """

    candidate_ids = set(candidates["comment_id"].astype(str))
    available = screened_development[
        ~screened_development["comment_id"].astype(str).isin(candidate_ids)
    ].copy()
    if "_supplementary_method" in available:
        available = available[available["_supplementary_method"].isna()].copy()

    used: set[str] = set()
    selected: list[pd.Series] = []
    for candidate in candidates.sort_values("comment_id", kind="mergesort").to_dict("records"):
        options = available[~available["comment_id"].astype(str).isin(used)]
        levels = (
            (
                "channel_script_time",
                (options["channel_name"] == candidate["channel_name"])
                & (options["script_category"] == candidate["script_category"])
                & (options["temporal_stratum"] == candidate["temporal_stratum"]),
            ),
            (
                "channel_script",
                (options["channel_name"] == candidate["channel_name"])
                & (options["script_category"] == candidate["script_category"]),
            ),
            ("channel", options["channel_name"] == candidate["channel_name"]),
            ("global", pd.Series(True, index=options.index)),
        )
        chosen: pd.Series | None = None
        chosen_level = ""
        for level, mask in levels:
            pool = options[mask].copy()
            if pool.empty:
                continue
            namespace = f"control:{candidate['comment_id']}:{level}"
            pool["_control_hash"] = pool["comment_id"].map(
                lambda value: _stable_hash(value, seed, namespace)
            )
            chosen = pool.sort_values(
                ["_control_hash", "comment_id"], kind="mergesort"
            ).iloc[0].drop(labels="_control_hash")
            chosen_level = level
            break
        if chosen is None:
            raise ValueError("Not enough unused development controls for all candidates")
        chosen = chosen.copy()
        chosen["selection_group"] = "matched_control"
        chosen["selection_source"] = "deterministic_matched_control"
        chosen["selection_reason"] = (
            "non-candidate control matched without using human labels"
        )
        chosen["matched_candidate_id"] = str(candidate["comment_id"])
        chosen["control_match_level"] = chosen_level
        used.add(str(chosen["comment_id"]))
        selected.append(chosen)
    return pd.DataFrame(selected).reset_index(drop=True)


def build_development_review_queue(
    eligible_source: pd.DataFrame,
    held_out_comments: pd.DataFrame,
    *,
    seed: int = EXPERIMENT_2A2_SEED,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build a blinded candidate/control queue only from development videos."""

    candidates, _, screened_development = build_demand_enriched_pool(
        eligible_source, held_out_comments, seed=seed
    )
    if candidates.empty:
        raise ValueError("No demand-enriched development candidates were retrieved")
    candidates = candidates.copy()
    candidates["selection_group"] = "demand_enriched_candidate"
    candidates["matched_candidate_id"] = ""
    candidates["control_match_level"] = "not_applicable"
    controls = select_matched_controls(screened_development, candidates, seed=seed)
    combined = pd.concat([candidates, controls], ignore_index=True, sort=False)
    combined = _order_for_review(combined, seed, "development-review")

    manifest_columns = [
        "review_order",
        "comment_id",
        "channel_id",
        "channel_name",
        "video_id",
        "temporal_stratum",
        "script_category",
        "selection_group",
        "selection_source",
        "selection_reason",
        "matched_candidate_id",
        "control_match_level",
        "_baseline_primary_signal",
        "_baseline_candidate",
        "_baseline_score",
        "_supplementary_method",
    ]
    manifest = combined[manifest_columns].rename(
        columns={
            "_baseline_primary_signal": "baseline_primary_signal",
            "_baseline_candidate": "baseline_candidate_for_content_demand",
            "_baseline_score": "baseline_score",
            "_supplementary_method": "supplementary_retrieval_method",
        }
    )
    template = create_blank_review_template(combined)
    return template, manifest


def build_exploratory_crosswalk(
    exploratory_path: str | Path,
    source: pd.DataFrame,
    calibration: pd.DataFrame,
    manifest: pd.DataFrame,
) -> pd.DataFrame:
    """Map the historical 500 rows to corrected roles without changing them."""

    path = Path(exploratory_path)
    if not path.exists():
        raise FileNotFoundError(f"Existing Experiment 2A sample is missing: {path}")
    exploratory = pd.read_csv(path, dtype={"comment_id": "string", "video_id": "string"})
    if len(exploratory) != 500 or exploratory["comment_id"].nunique() != 500:
        raise ValueError("Existing Experiment 2A sample must contain 500 unique comments")
    if "video_id" not in exploratory:
        mapping = source.set_index("comment_id")["video_id"]
        exploratory["video_id"] = exploratory["comment_id"].map(mapping)
    role_lookup = manifest.set_index("video_id")["dataset_role"]
    calibration_ids = set(calibration["comment_id"].astype(str))
    crosswalk = exploratory[["comment_id", "video_id", "channel_id", "channel_name"]].copy()
    crosswalk["historical_dataset_role"] = "exploratory_annotation_pool"
    crosswalk["corrected_video_role"] = crosswalk["video_id"].astype(str).map(role_lookup)
    crosswalk["exact_calibration_comment_overlap"] = crosswalk["comment_id"].astype(str).isin(
        calibration_ids
    )
    if crosswalk["corrected_video_role"].isna().any():
        raise ValueError("Existing 500-comment sample contains a video absent from the pilot manifest")
    return crosswalk


def validate_outputs(
    source: pd.DataFrame,
    calibration: pd.DataFrame,
    video_manifest: pd.DataFrame,
    comment_manifest: pd.DataFrame,
    held_out_template: pd.DataFrame,
    development_template: pd.DataFrame,
    development_manifest: pd.DataFrame,
    exploratory_crosswalk: pd.DataFrame,
) -> dict[str, Any]:
    """Validate leakage, completeness, blank labels, and historical isolation."""

    roles = set(video_manifest["dataset_role"])
    expected_roles = {"calibration_only", "held_out_evaluation", "development_pool"}
    if roles != expected_roles:
        raise ValueError(f"Unexpected video roles: {sorted(roles)}")
    if video_manifest["video_id"].duplicated().any():
        raise ValueError("A video appears more than once in the partition manifest")
    if len(comment_manifest) != len(source) or comment_manifest["comment_id"].nunique() != len(source):
        raise ValueError("Comment partition manifest does not cover each source comment once")
    if set(comment_manifest["comment_id"].astype(str)) != set(source["comment_id"].astype(str)):
        raise ValueError("Comment partition manifest does not preserve the exact source IDs")
    if comment_manifest.groupby("video_id")["dataset_role"].nunique().max() != 1:
        raise ValueError("At least one video crosses dataset roles")

    calibration_videos = set(
        video_manifest.loc[
            video_manifest["dataset_role"].eq("calibration_only"), "video_id"
        ].astype(str)
    )
    expected_calibration_videos = calibration_video_ids(source, calibration)
    if calibration_videos != expected_calibration_videos:
        raise ValueError("Calibration video exclusions do not match the frozen calibration rows")

    held_out_ids = set(held_out_template["comment_id"].astype(str))
    expected_held_out = set(
        comment_manifest.loc[
            comment_manifest["dataset_role"].eq("held_out_evaluation"), "comment_id"
        ].astype(str)
    )
    if held_out_ids != expected_held_out:
        raise ValueError("Held-out reviewer template is incomplete or contains extra comments")
    if set(held_out_template["video_id"].astype(str)).intersection(calibration_videos):
        raise ValueError("Held-out evaluation includes a calibration video")

    for name, frame in (
        ("held-out", held_out_template),
        ("development", development_template),
    ):
        validate_annotation_frame(frame)
        nonblank = {
            column: int(frame[column].fillna("").astype(str).str.strip().ne("").sum())
            for column in REVIEW_ANNOTATION_FIELDS
        }
        if any(nonblank.values()):
            raise ValueError(f"{name} template contains nonblank human annotations: {nonblank}")
        if frame["comment_id"].duplicated().any():
            raise ValueError(f"{name} template contains duplicate comment IDs")

    development_video_ids = set(
        video_manifest.loc[
            video_manifest["dataset_role"].eq("development_pool"), "video_id"
        ].astype(str)
    )
    if not set(development_template["video_id"].astype(str)).issubset(development_video_ids):
        raise ValueError("Development review queue contains a non-development video")
    group_counts = development_manifest["selection_group"].value_counts().to_dict()
    if group_counts.get("demand_enriched_candidate", 0) != group_counts.get(
        "matched_control", 0
    ):
        raise ValueError("Development candidate and matched-control counts differ")
    if set(held_out_template["comment_id"]).intersection(development_template["comment_id"]):
        raise ValueError("Held-out and development review templates share comments")
    if len(exploratory_crosswalk) != 500:
        raise ValueError("Exploratory crosswalk does not preserve all 500 historical rows")

    video_counts = video_manifest["dataset_role"].value_counts().to_dict()
    comment_counts = comment_manifest["dataset_role"].value_counts().to_dict()
    return {
        "source_rows": len(source),
        "source_unique_videos": int(source["video_id"].nunique()),
        "calibration_rows": len(calibration),
        "calibration_unique_videos": len(calibration_videos),
        "video_role_counts": {key: int(value) for key, value in video_counts.items()},
        "comment_role_counts": {key: int(value) for key, value in comment_counts.items()},
        "held_out_channel_counts": held_out_template["channel_name"].value_counts().sort_index().to_dict(),
        "held_out_script_counts": held_out_template["script_category"].value_counts().sort_index().to_dict(),
        "development_review_rows": len(development_template),
        "development_review_unique_videos": int(development_template["video_id"].nunique()),
        "development_review_group_counts": {
            key: int(value) for key, value in group_counts.items()
        },
        "development_review_channel_counts": development_template["channel_name"].value_counts().sort_index().to_dict(),
        "development_selection_sources": development_manifest["selection_source"].value_counts().to_dict(),
        "development_control_match_levels": (
            development_manifest.loc[
                development_manifest["selection_group"].eq("matched_control"),
                "control_match_level",
            ]
            .value_counts()
            .to_dict()
        ),
        "exploratory_exact_calibration_overlap": int(
            exploratory_crosswalk["exact_calibration_comment_overlap"].sum()
        ),
        "exploratory_role_counts": exploratory_crosswalk["corrected_video_role"].value_counts().to_dict(),
    }


def _render_report(summary: dict[str, Any], seed: int) -> str:
    video_roles = summary["video_role_counts"]
    comment_roles = summary["comment_role_counts"]
    return f"""# Experiment 2A.2: Corrected Video-Grouped Sampling Frame

## Decision

The historical 500-comment sample remains unchanged and is now treated as an
exploratory annotation pool, not a final held-out test. Experiment 2A.2 creates
a new split at the video level before any new annotation or model training.

## Reproducible design

- Seed: `{seed}`
- Source: `{summary['source_rows']}` comments across `{summary['source_unique_videos']}` comment-covered videos
- Frozen calibration: `{summary['calibration_rows']}` comments across `{summary['calibration_unique_videos']}` videos
- Calibration handling: every comment from a calibration video is assigned to `calibration_only`
- Eligible-video sampling: stable-hash simple random sampling without replacement within channel and within-channel chronological quartile
- Target held-out video fraction: `0.20`
- Model-selection plan: retain one held-out evaluation partition and use grouped validation within the development pool later

Selection does not use comment text, rule predictions, human labels, script
category, or programme assumptions. Exact stratum probabilities and inverse
weights are stored in the local video manifest.

## Resulting partitions

| Role | Videos | Comments |
| --- | ---: | ---: |
| Calibration only | {video_roles.get('calibration_only', 0)} | {comment_roles.get('calibration_only', 0)} |
| Held-out evaluation | {video_roles.get('held_out_evaluation', 0)} | {comment_roles.get('held_out_evaluation', 0)} |
| Development pool | {video_roles.get('development_pool', 0)} | {comment_roles.get('development_pool', 0)} |

Held-out comments by channel: `{summary['held_out_channel_counts']}`.

Held-out comments by script category: `{summary['held_out_script_counts']}`.

The development review queue contains `{summary['development_review_rows']}`
rows: `{summary['development_review_group_counts']}`. Candidate retrieval and
matched-control provenance are kept in a separate local manifest. The blinded
review CSV contains no candidate flags or model predictions, and every human
annotation field is blank.

Development selection sources: `{summary['development_selection_sources']}`.
Control matching levels: `{summary['development_control_match_levels']}`.

## Historical sample crosswalk

The earlier 500 rows are preserved exactly. Their corrected video roles are
`{summary['exploratory_role_counts']}`. Exact calibration-comment overlap is
`{summary['exploratory_exact_calibration_overlap']}` rows. This crosswalk
prevents the old pool from being mislabeled as an independent final test.

The crosswalk includes {summary['exploratory_role_counts'].get('held_out_evaluation', 0)} rows now assigned to held-out evaluation. Before
those rows are treated as sealed test data, the researcher must confirm
whether anyone previously inspected their text or labels and whether any rule
or threshold was tuned using them. Experiment 2A.2 records the exposure but
does not assume an answer or silently replace the frozen partition.

## Interpretation and limits

This is representative only of the calibration-excluded, five-channel local
pilot under a clustered video-sampling design. It does not establish
generalization to all YouTube viewers, other periods, or the organization's
full catalogue. Comments from one video are correlated, so later uncertainty
estimates and cross-validation must retain `video_id` as the group.

Programme name and content type are not reliably structured in the local
metadata. They were therefore not guessed or used to choose the split. Before
programme-level claims or demand-supply comparison, those fields require a
documented manual or source-verified metadata audit.

The templates contain no new ground truth. Independent human annotation,
agreement measurement, and adjudication remain prerequisites for supervised
learning. No baseline was tuned, no model was trained, and no API or database
was accessed.
"""


def prepare(
    *,
    comments_path: str | Path = DEFAULT_PILOT_COMMENTS,
    videos_path: str | Path = DEFAULT_PILOT_VIDEOS,
    preprocessed_path: str | Path = DEFAULT_PREPROCESSED,
    calibration_path: str | Path = DEFAULT_CALIBRATION,
    exploratory_path: str | Path = DEFAULT_EXPLORATORY_SAMPLE,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    seed: int = EXPERIMENT_2A2_SEED,
    held_out_fraction: float = HELD_OUT_VIDEO_FRACTION,
    temporal_strata: int = TEMPORAL_STRATA,
) -> dict[str, Any]:
    """Run Experiment 2A.2 locally and write only Git-ignored artifacts."""

    output = Path(output_dir)
    partition_lock = load_partition_lock()
    if seed != int(partition_lock["split_seed"]):
        raise ValueError(
            "Experiment 2A.2 is frozen; the requested seed differs from the partition lock"
        )
    input_hashes = {
        "comments": sha256(comments_path),
        "videos": sha256(videos_path),
        "preprocessed": sha256(preprocessed_path),
        "calibration": sha256(calibration_path),
        "exploratory_sample": sha256(exploratory_path),
    }
    expected_input_hashes = partition_lock.get("input_sha256", {})
    if input_hashes != expected_input_hashes:
        raise ValueError(
            "Experiment 2A.2 inputs differ from the frozen partition lock; "
            "do not regenerate or replace the held-out split without approval"
        )
    source = build_experiment_source(comments_path, videos_path, preprocessed_path)
    calibration = load_calibration_frame(calibration_path)
    video_manifest = create_video_partition_manifest(
        source,
        calibration,
        videos_path=videos_path,
        seed=seed,
        held_out_fraction=held_out_fraction,
        temporal_strata=temporal_strata,
    )
    partitioned = attach_video_partitions(source, video_manifest)
    comment_manifest = partitioned[
        [
            "comment_id",
            "video_id",
            "channel_id",
            "channel_name",
            "dataset_role",
            "temporal_stratum",
            "video_published_at",
            "video_selection_probability",
            "sampling_weight",
        ]
    ].copy()
    partition_guard = PartitionGuard.verify(
        comment_manifest,
        partition_lock,
    )

    held_out = partitioned[partitioned["dataset_role"].eq("held_out_evaluation")].copy()
    held_out = _order_for_review(held_out, seed, "held-out-review")
    held_out_template = create_blank_review_template(held_out)

    eligible = partitioned[~partitioned["dataset_role"].eq("calibration_only")].copy()
    development_template, development_manifest = build_development_review_queue(
        eligible, held_out, seed=seed
    )
    exploratory_crosswalk = build_exploratory_crosswalk(
        exploratory_path, source, calibration, video_manifest
    )
    summary = validate_outputs(
        source,
        calibration,
        video_manifest,
        comment_manifest,
        held_out_template,
        development_template,
        development_manifest,
        exploratory_crosswalk,
    )
    summary.update(
        {
            "seed": seed,
            "held_out_video_fraction_target": held_out_fraction,
            "temporal_strata": temporal_strata,
            "partition_manifest_fingerprint": partition_guard.fingerprint,
            "partition_fingerprint_algorithm": partition_guard.lock[
                "fingerprint_algorithm"
            ],
            "input_sha256": input_hashes,
        }
    )

    _write_csv(output / "video_partition_manifest.csv", video_manifest)
    _write_csv(output / "comment_partition_manifest.csv", comment_manifest)
    _write_csv(output / "held_out_evaluation_comments.csv", held_out_template)
    _write_csv(output / "development_candidate_control_review.csv", development_template)
    _write_csv(output / "development_selection_manifest.csv", development_manifest)
    _write_csv(output / "exploratory_500_crosswalk.csv", exploratory_crosswalk)
    _write_json(output / "dataset_summary.json", summary)
    (output / "experiment_2a2_report.md").write_text(
        _render_report(summary, seed), encoding="utf-8"
    )
    return {"output_dir": str(output), "summary": summary}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comments", type=Path, default=DEFAULT_PILOT_COMMENTS)
    parser.add_argument("--videos", type=Path, default=DEFAULT_PILOT_VIDEOS)
    parser.add_argument("--preprocessed", type=Path, default=DEFAULT_PREPROCESSED)
    parser.add_argument("--calibration", type=Path, default=DEFAULT_CALIBRATION)
    parser.add_argument("--exploratory-sample", type=Path, default=DEFAULT_EXPLORATORY_SAMPLE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--seed", type=int, default=EXPERIMENT_2A2_SEED)
    parser.add_argument("--held-out-fraction", type=float, default=HELD_OUT_VIDEO_FRACTION)
    parser.add_argument("--temporal-strata", type=int, default=TEMPORAL_STRATA)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = prepare(
        comments_path=args.comments,
        videos_path=args.videos,
        preprocessed_path=args.preprocessed,
        calibration_path=args.calibration,
        exploratory_path=args.exploratory_sample,
        output_dir=args.output_dir,
        seed=args.seed,
        held_out_fraction=args.held_out_fraction,
        temporal_strata=args.temporal_strata,
    )
    summary = result["summary"]
    print(f"Video roles: {summary['video_role_counts']}")
    print(f"Comment roles: {summary['comment_role_counts']}")
    print(f"Development review rows: {summary['development_review_rows']}")
    print(f"Outputs: {result['output_dir']}")


if __name__ == "__main__":
    main()
