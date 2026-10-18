"""Prepare reproducible, video-aware Experiment 2A annotation datasets."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from research.component_2.src.annotation import assign_sampling_stratum, combine_preprocessing_flags
from research.component_2.src.data_io import load_comments, load_videos

from .annotation_schema import (
    ACTIONABILITY_LABELS,
    ANNOTATION_SCHEMA_VERSION,
    EVIDENCE_TEXT_FIELD,
    PRIMARY_SIGNALS,
    REVIEW_ANNOTATION_FIELDS,
    TEXT_PROVENANCE_VERSION,
    normalized_text,
    raw_text_sha256,
    validate_annotation_frame,
)
from .audit import build_pilot_frame, CHANNEL_TYPES, sha256
from .baseline import detect_frame
from .config import (
    DEFAULT_PILOT_COMMENTS,
    DEFAULT_PILOT_VIDEOS,
    DEFAULT_PREPROCESSED,
)


EXPERIMENT_2A_SEED = 20261016
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "outputs" / "experiment_2a"
REPRESENTATIVE_PER_CHANNEL = 100
REVIEW_CONTEXT_FIELDS = [
    "review_order",
    "comment_id",
    "channel_id",
    "channel_name",
    "channel_type",
    "video_id",
    "video_title",
    "video_description",
    "video_url",
    "parent_comment_id",
    "parent_comment_text",
    "parent_context_status",
    "video_context_status",
    "published_at",
    "is_reply",
    "annotation_schema_version",
    "text_provenance_version",
    "raw_comment_text",
    "raw_comment_text_sha256",
    "normalized_text",
    "evidence_text_field",
    "original_text",
    "cleaned_text",
    "script_category",
    "preprocessing_flags",
    "sampling_stratum",
]

SUPPLEMENTARY_RETRIEVAL_PATTERNS = (
    (
        "reupload_or_full_version_phrase",
        (
            r"\bre[- ]?upload\b",
            r"\bfull\s+(?:video|episode|version)\b",
            r"\bcomplete\s+(?:video|episode|version)\b",
            r"\bpart\s*2\b",
            r"\b(?:again|once\s+more)\b",
            r"(?:නැවත|ආයෙ|ආයෙත්)",
        ),
    ),
    (
        "language_or_accessibility_phrase",
        (
            r"\bsubtitles?\b",
            r"\b(?:translate|translation|caption)\b",
            r"\b(?:sinhala|tamil|english)\s+(?:version|subtitles?|walin)\b",
            r"(?:උපසිරැසි|පරිවර්තනය)",
        ),
    ),
    (
        "cast_or_storyline_preference_phrase",
        (
            r"\bbring\s+(?:him|her|them)\s+back\b",
            r"\bkeep\s+(?:them|the\s+characters?)\s+(?:as|together)\b",
            r"\b(?:judge|judges|cast|character|storyline)\b.{0,40}\b(?:change|back|keep|bring)\b",
        ),
    ),
)


def _normalise_parent_id(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = "" if value is None else str(value).strip()
    return "" if text.casefold() in {"", "null", "none", "nan"} else text


def _channel_seed(seed: int, channel: str) -> int:
    digest = hashlib.sha256(f"{seed}:{channel}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _stable_row_order(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.sort_values(["comment_id"], kind="mergesort").reset_index(drop=True)


def build_experiment_source(
    comments_path: str | Path = DEFAULT_PILOT_COMMENTS,
    videos_path: str | Path = DEFAULT_PILOT_VIDEOS,
    preprocessed_path: str | Path = DEFAULT_PREPROCESSED,
) -> pd.DataFrame:
    """Load local pilot data and explicitly mark unavailable reply context."""

    frame = build_pilot_frame(comments_path, videos_path, preprocessed_path).copy()
    comments = load_comments(comments_path).copy()
    videos = load_videos(videos_path).copy()
    raw_source = pd.read_csv(
        comments_path,
        usecols=["comment_id", "comment_text"],
        dtype={"comment_id": "string", "comment_text": "string"},
        keep_default_na=False,
    )
    if raw_source["comment_id"].duplicated().any():
        raise ValueError("Pilot source contains duplicate comment IDs")
    raw_text_lookup = raw_source.set_index("comment_id")["comment_text"]
    frame["raw_comment_text"] = frame["comment_id"].map(raw_text_lookup)
    if frame["raw_comment_text"].isna().any():
        raise ValueError("Pilot source is missing raw text for at least one comment")
    frame["normalized_text"] = frame["raw_comment_text"].map(normalized_text)
    frame["raw_comment_text_sha256"] = frame["raw_comment_text"].map(raw_text_sha256)
    frame["text_provenance_version"] = TEXT_PROVENANCE_VERSION
    frame["evidence_text_field"] = EVIDENCE_TEXT_FIELD
    comments["parent_comment_id_normalized"] = comments["parent_comment_id"].map(_normalise_parent_id)
    local_comment_text = {
        str(row["comment_id"]): str(row["comment_text"])
        for row in comments.to_dict("records")
        if str(row.get("comment_text", "")).strip()
    }
    parent_ids = comments.set_index("comment_id")["parent_comment_id_normalized"].to_dict()
    frame["parent_comment_id"] = frame["comment_id"].map(parent_ids).fillna("")
    frame["is_reply"] = frame["parent_comment_id"].astype(str).str.strip().ne("")
    frame["parent_comment_text"] = frame["parent_comment_id"].map(local_comment_text).fillna("")
    frame["parent_context_status"] = "not_a_reply"
    frame.loc[frame["is_reply"] & frame["parent_comment_text"].ne(""), "parent_context_status"] = "available_from_local_pilot"
    frame.loc[frame["is_reply"] & frame["parent_comment_text"].eq(""), "parent_context_status"] = "missing_parent_context"
    frame["video_context_status"] = "complete"
    frame.loc[frame["video_title"].eq("") | frame["video_description"].eq(""), "video_context_status"] = "partial"
    frame["channel_type"] = frame["channel_name"].map(CHANNEL_TYPES).fillna("unknown")
    frame["preprocessing_flags"] = frame.apply(combine_preprocessing_flags, axis=1)
    frame["sampling_stratum"] = frame.apply(assign_sampling_stratum, axis=1)
    frame["source_dataset"] = Path(comments_path).name
    frame["source_videos_dataset"] = Path(videos_path).name
    if frame["comment_id"].duplicated().any():
        raise ValueError("Pilot source contains duplicate comment IDs")
    if frame["video_id"].isna().any() or frame["channel_name"].isna().any():
        raise ValueError("Pilot source contains comments without video or channel provenance")
    if len(videos) == 0:
        raise ValueError("Pilot video metadata is empty")
    return frame


def select_representative_sample(
    source: pd.DataFrame,
    *,
    seed: int = EXPERIMENT_2A_SEED,
    per_channel: int = REPRESENTATIVE_PER_CHANNEL,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Sample comments uniformly within each channel without language enrichment."""

    channels = sorted(source["channel_name"].dropna().unique())
    if not channels:
        raise ValueError("No channels available for representative sampling")
    selected: list[pd.DataFrame] = []
    manifest: list[dict[str, Any]] = []
    for channel in channels:
        channel_frame = _stable_row_order(source[source["channel_name"] == channel])
        if len(channel_frame) < per_channel:
            raise ValueError(f"Channel {channel} has only {len(channel_frame)} rows; cannot sample {per_channel}")
        rng = random.Random(_channel_seed(seed, channel))
        selected_positions = sorted(rng.sample(range(len(channel_frame)), per_channel))
        chosen = channel_frame.iloc[selected_positions].copy()
        probability = per_channel / len(channel_frame)
        chosen["selection_probability"] = probability
        chosen["sampling_weight"] = 1.0 / probability
        chosen["channel_population_size"] = len(channel_frame)
        chosen["channel_target_size"] = per_channel
        selected.append(chosen)
        for _, row in chosen.iterrows():
            manifest.append(
                {
                    "comment_id": row["comment_id"],
                    "channel_id": row["channel_id"],
                    "channel_name": channel,
                    "video_id": row["video_id"],
                    "dataset_role": "representative_evaluation",
                    "sampling_seed": seed,
                    "sampling_method": "uniform_within_channel_without_replacement",
                    "channel_population_size": len(channel_frame),
                    "channel_target_size": per_channel,
                    "selection_probability": probability,
                    "sampling_weight": 1.0 / probability,
                    "selection_provenance": "all eligible pilot comments in channel; no keyword or language enrichment",
                }
            )
    sample = pd.concat(selected, ignore_index=True)
    shuffle_rng = random.Random(seed)
    order = list(range(len(sample)))
    shuffle_rng.shuffle(order)
    sample = sample.iloc[order].reset_index(drop=True)
    sample["review_order"] = range(1, len(sample) + 1)
    order_by_id = dict(zip(sample["comment_id"], sample["review_order"], strict=True))
    manifest_frame = pd.DataFrame(manifest)
    manifest_frame["review_order"] = manifest_frame["comment_id"].map(order_by_id)
    manifest_frame = manifest_frame.sort_values("review_order").reset_index(drop=True)
    return sample, manifest_frame


def _supplementary_retrieval_reason(text: object) -> str | None:
    normalized = "" if text is None else str(text)
    for method, patterns in SUPPLEMENTARY_RETRIEVAL_PATTERNS:
        if any(re.search(pattern, normalized, flags=re.IGNORECASE | re.UNICODE) for pattern in patterns):
            return method
    return None


def build_demand_enriched_pool(
    source: pd.DataFrame,
    representative: pd.DataFrame,
    *,
    seed: int = EXPERIMENT_2A_SEED,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build an enriched review pool from videos excluded from evaluation."""

    representative_videos = set(representative["video_id"].astype(str))
    remaining = source[~source["video_id"].astype(str).isin(representative_videos)].copy()
    predictions = detect_frame(remaining).reset_index(drop=True)
    remaining = remaining.reset_index(drop=True)
    remaining["_baseline_candidate"] = predictions["candidate_for_content_demand"].astype(bool)
    remaining["_baseline_primary_signal"] = predictions["primary_signal"]
    remaining["_baseline_score"] = predictions["baseline_score"]
    remaining["_supplementary_method"] = remaining["original_text"].map(_supplementary_retrieval_reason)

    rule_candidates = remaining[remaining["_baseline_candidate"]].copy()
    rule_candidates["selection_source"] = "existing_rule_candidate"
    rule_candidates["selection_reason"] = "baseline.detect_comment candidate_for_content_demand=True"
    supplementary = remaining[
        (~remaining["_baseline_candidate"]) & remaining["_supplementary_method"].notna()
    ].copy()
    supplementary["selection_source"] = "supplementary_phrase_retrieval"
    supplementary["selection_reason"] = supplementary["_supplementary_method"].map(
        lambda value: f"transparent retrieval pattern: {value}"
    )
    pool = pd.concat([rule_candidates, supplementary], ignore_index=True)
    pool = pool.drop_duplicates("comment_id").copy()
    pool["selection_seed"] = seed
    pool["representative_video_excluded"] = True
    pool = _stable_row_order(pool)
    rng = random.Random(seed + 1)
    order = list(range(len(pool)))
    rng.shuffle(order)
    pool = pool.iloc[order].reset_index(drop=True)
    pool["review_order"] = range(1, len(pool) + 1)

    manifest_columns = [
        "review_order", "comment_id", "channel_id", "channel_name", "video_id", "selection_source",
        "selection_reason", "selection_seed", "baseline_primary_signal", "baseline_candidate_for_content_demand",
        "baseline_score", "representative_video_excluded",
    ]
    manifest = pool.rename(
        columns={
            "_baseline_primary_signal": "baseline_primary_signal",
            "_baseline_candidate": "baseline_candidate_for_content_demand",
            "_baseline_score": "baseline_score",
        }
    )[manifest_columns].copy()
    return pool, manifest, remaining


def create_blank_review_template(frame: pd.DataFrame) -> pd.DataFrame:
    """Create a reviewer-facing template without baseline selection fields."""

    template = frame.copy()
    template["annotation_schema_version"] = ANNOTATION_SCHEMA_VERSION
    template["text_provenance_version"] = TEXT_PROVENANCE_VERSION
    template["evidence_text_field"] = EVIDENCE_TEXT_FIELD
    if "raw_comment_text" not in template:
        template["raw_comment_text"] = template.get("original_text", "")
    if "normalized_text" not in template:
        template["normalized_text"] = template["raw_comment_text"].map(normalized_text)
    if "raw_comment_text_sha256" not in template:
        template["raw_comment_text_sha256"] = template["raw_comment_text"].map(
            raw_text_sha256
        )
    for column in REVIEW_ANNOTATION_FIELDS:
        template[column] = ""
    for column in REVIEW_CONTEXT_FIELDS:
        if column not in template:
            template[column] = ""
    template = template[REVIEW_CONTEXT_FIELDS + REVIEW_ANNOTATION_FIELDS].copy()
    validate_annotation_frame(template)
    return template


def create_video_split_manifest(
    source: pd.DataFrame,
    representative: pd.DataFrame,
    enriched: pd.DataFrame,
    *,
    seed: int = EXPERIMENT_2A_SEED,
) -> pd.DataFrame:
    representative_videos = set(representative["video_id"].astype(str))
    enriched_videos = set(enriched["video_id"].astype(str))
    if representative_videos.intersection(enriched_videos):
        raise ValueError("Representative and demand-enriched datasets share video IDs")
    videos = source[["video_id", "channel_id", "channel_name"]].drop_duplicates("video_id").copy()
    videos["video_id"] = videos["video_id"].astype(str)
    videos["video_split"] = "training_pool_unlabelled"
    videos.loc[videos["video_id"].isin(enriched_videos), "video_split"] = "development_demand_enriched"
    videos.loc[videos["video_id"].isin(representative_videos), "video_split"] = "test_representative"
    videos["split_seed"] = seed
    videos["split_rule"] = "all comments from a video remain in one future partition"
    return videos.sort_values(["video_split", "channel_name", "video_id"]).reset_index(drop=True)


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def validate_prepared_outputs(
    source: pd.DataFrame,
    representative: pd.DataFrame,
    representative_manifest: pd.DataFrame,
    enriched: pd.DataFrame,
    enriched_manifest: pd.DataFrame,
    split_manifest: pd.DataFrame,
) -> dict[str, Any]:
    if len(representative) != 500:
        raise ValueError(f"Representative sample must contain 500 rows, found {len(representative)}")
    if representative["comment_id"].duplicated().any() or enriched["comment_id"].duplicated().any():
        raise ValueError("Prepared datasets contain duplicate comment IDs")
    if set(representative["comment_id"]).intersection(enriched["comment_id"]):
        raise ValueError("Representative and enriched datasets share comment IDs")
    if set(representative["video_id"]).intersection(enriched["video_id"]):
        raise ValueError("Representative and enriched datasets share video IDs")
    representative_counts = representative["channel_name"].value_counts().sort_index().to_dict()
    if set(representative_counts.values()) != {100} or len(representative_counts) != 5:
        raise ValueError(f"Representative channel counts are not 100 each: {representative_counts}")
    if len(representative_manifest) != len(representative) or len(enriched_manifest) != len(enriched):
        raise ValueError("Manifest row counts do not match prepared datasets")
    for frame in (representative, enriched):
        nonblank = {
            column: int(frame[column].fillna("").astype(str).str.strip().ne("").sum())
            for column in REVIEW_ANNOTATION_FIELDS
            if column in frame
        }
        if any(nonblank.values()):
            raise ValueError(f"Prepared template contains nonblank human fields: {nonblank}")
    if set(split_manifest.loc[split_manifest["video_split"] == "test_representative", "video_id"]) != set(representative["video_id"]):
        raise ValueError("Video split manifest does not mark all representative videos as test_representative")
    if set(split_manifest.loc[split_manifest["video_split"] == "development_demand_enriched", "video_id"]) != set(enriched["video_id"]):
        raise ValueError("Video split manifest does not mark all enriched videos as development_demand_enriched")
    return {
        "source_rows": len(source),
        "source_unique_comments": int(source["comment_id"].nunique()),
        "source_unique_videos": int(source["video_id"].nunique()),
        "representative_rows": len(representative),
        "representative_unique_videos": int(representative["video_id"].nunique()),
        "representative_channel_counts": representative_counts,
        "demand_enriched_rows": len(enriched),
        "demand_enriched_unique_videos": int(enriched["video_id"].nunique()),
        "demand_enriched_channel_counts": enriched["channel_name"].value_counts().sort_index().to_dict(),
    }


def _render_methodology(
    source: pd.DataFrame,
    representative: pd.DataFrame,
    representative_manifest: pd.DataFrame,
    enriched: pd.DataFrame,
    enriched_manifest: pd.DataFrame,
    validation: dict[str, Any],
    seed: int,
) -> str:
    parent_counts = source["parent_context_status"].value_counts().to_dict()
    video_context_counts = source["video_context_status"].value_counts().to_dict()
    methods = enriched_manifest["selection_source"].value_counts().to_dict()
    script_counts = source["script_category"].value_counts().sort_index().to_dict()
    return f"""# Experiment 2A: Multilingual Dataset Preparation

## Status and scope

This preparation run is offline and reproducible. It uses the local Component 2
pilot only; it does not access Supabase, YouTube, external APIs, or the
production annotation portal. The existing 40-comment calibration annotations
and `baseline.py` were read only and remain unchanged.

- Seed: `{seed}`
- Exact input-file SHA-256 values are recorded in `dataset_availability.json`.
- Source comments: `{validation['source_rows']}` rows and `{validation['source_unique_comments']}` unique IDs
- Source videos with comments: `{validation['source_unique_videos']}`
- Source channels: `{source['channel_name'].nunique()}`
- Representative evaluation rows: `{validation['representative_rows']}`
- Demand-enriched rows: `{validation['demand_enriched_rows']}`

## Availability and quality

The pilot contains 2,000 comments, balanced at 400 comments per each of five
channels. Those comments cover 255 unique videos. The raw video catalog contains
327 records; comments therefore do not cover every catalog video. Video titles
and descriptions are available for the pilot rows used here.

Existing script categories in the 2,000 comments are:

`{script_counts}`

Reply provenance is incomplete. Parent IDs are available for 367 rows; the
corresponding parent comment text is present locally for 123 rows, while 244
reply rows have a parent ID whose text is unavailable in the pilot. These rows
are marked `missing_parent_context`; no parent text was invented.

Video context status: `{video_context_counts}`. Parent context status:
`{parent_counts}`.

## Representative evaluation sample

The representative sample selects exactly 100 comments per channel using
uniform sampling without replacement within each channel. No keyword, rule
candidate, script, language, or sentiment enrichment is used. Because each
channel contains 400 comments, each source comment has an inclusion probability
of 0.25 within its channel and a design weight of 4.0.

The sample contains `{validation['representative_unique_videos']}` unique videos.
The sampling manifest preserves the seed, channel population, target, inclusion
probability, weight, video ID, and source provenance. The reviewer-facing CSV
does not expose baseline candidate flags or selection source.

The existing eight primary signals remain unchanged: `EXPLICIT_CONTENT_REQUEST`,
`CONTENT_CHANGE_PREFERENCE`, `INFORMATION_NEED`, `CONTENT_QUALITY_FEEDBACK`,
`TOPICAL_INTEREST_OR_DISCUSSION`, `ORDINARY_REACTION`, `SPAM_OR_IRRELEVANT`,
and `UNCLEAR`. Actionability remains `YES`, `NO`, or `UNCLEAR`.

## Demand-enriched sample

The demand-enriched pool is separate and is not a prevalence sample. It uses
existing `baseline.detect_comment()` candidates plus a transparent supplementary
phrase-retrieval pass for re-upload/full-version, language/accessibility, and
cast/storyline-preference expressions. Selection methods are retained in a
separate manifest, not in the reviewer-facing template.

Rows whose videos occur in the representative sample are excluded first. This
prevents comment-level and video-level leakage between evaluation and enriched
development data. Retrieval method counts are `{methods}` and channel counts
are `{validation['demand_enriched_channel_counts']}`.

Only `{validation['demand_enriched_rows']}` rows remained after the video-level
exclusion in this local pilot, and they come from only two channels. This is
useful as a provenance check and a small targeted review queue, but it is not
large or balanced enough for supervised training, multilingual coverage claims,
or prevalence estimation.

## Blank annotation procedure

Both templates contain exact raw text, its UTF-8 hash, separate NFC-normalized
and cleaned text, video title/description, video URL, reply metadata, script
category, sampling stratum, and explicit context-availability fields. All
annotation fields are blank. The templates include independent annotator
IDs/statuses, primary signal, secondary signals, actionability (`YES`, `NO`,
`UNCLEAR`), request details, spam status, and final adjudication fields.

Recommended procedure:

1. Annotator 1 and Annotator 2 label their assigned rows independently.
2. Preserve annotator ID and status without overwriting the other annotation.
3. Record `UNCLEAR` when missing parent context or language ambiguity prevents
   a confident decision.
4. Adjudicate disagreements using the existing eight primary categories and
   three actionability labels; retain both independent labels and the reason.
5. Do not copy rule predictions into human fields.

## Video-grouped separation

The split manifest marks representative videos as `test_representative`,
demand-enriched videos as `development_demand_enriched`, and remaining videos
as `training_pool_unlabelled`. Every comment from a video stays in one future
partition. No model training is performed by this experiment.

## Limitations

The pilot supports a 500-row channel-balanced evaluation sample, but it is not
necessarily representative of all organization channels, time periods, or
YouTube viewers. Equal channel allocation is appropriate for this balanced
pilot; if future source channel sizes differ, report design weights or sample
proportionally. The demand-enriched pool is intentionally biased toward
possible requests and must not be used to estimate demand prevalence or final
generalization.

The existing local data do not supply parent text for all replies. Additional
collection would be justified to enlarge the demand-enriched queue or recover
parent context, but it requires explicit approval and a new snapshot. This run
records the missingness instead and makes no external API request.
"""


def prepare(
    *,
    comments_path: str | Path = DEFAULT_PILOT_COMMENTS,
    videos_path: str | Path = DEFAULT_PILOT_VIDEOS,
    preprocessed_path: str | Path = DEFAULT_PREPROCESSED,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    seed: int = EXPERIMENT_2A_SEED,
    per_channel: int = REPRESENTATIVE_PER_CHANNEL,
) -> dict[str, Any]:
    output = Path(output_dir)
    source = build_experiment_source(comments_path, videos_path, preprocessed_path)
    representative, representative_manifest = select_representative_sample(
        source, seed=seed, per_channel=per_channel
    )
    enriched_pool, enriched_manifest, remaining = build_demand_enriched_pool(
        source, representative, seed=seed
    )
    representative_template = create_blank_review_template(representative)
    enriched_template = create_blank_review_template(enriched_pool)
    split_manifest = create_video_split_manifest(source, representative, enriched_pool, seed=seed)
    validation = validate_prepared_outputs(
        source,
        representative_template,
        representative_manifest,
        enriched_template,
        enriched_manifest,
        split_manifest,
    )

    _write_csv(output / "representative_evaluation_500.csv", representative_template)
    _write_csv(output / "representative_sampling_manifest.csv", representative_manifest)
    _write_csv(output / "demand_enriched_candidates.csv", enriched_template)
    _write_csv(output / "demand_enriched_selection_manifest.csv", enriched_manifest)
    _write_csv(output / "video_split_manifest.csv", split_manifest)
    _write_json(
        output / "dataset_availability.json",
        {
            "seed": seed,
            "input_files": {
                "comments": {"name": Path(comments_path).name, "sha256": sha256(comments_path)},
                "videos": {"name": Path(videos_path).name, "sha256": sha256(videos_path)},
                "preprocessed": {"name": Path(preprocessed_path).name, "sha256": sha256(preprocessed_path)},
            },
            "source_rows": len(source),
            "source_unique_comments": int(source["comment_id"].nunique()),
            "source_unique_videos": int(source["video_id"].nunique()),
            "source_channel_counts": source["channel_name"].value_counts().sort_index().to_dict(),
            "source_script_counts": source["script_category"].value_counts().sort_index().to_dict(),
            "source_script_counts_by_channel": {
                str(channel): group["script_category"].value_counts().sort_index().to_dict()
                for channel, group in source.groupby("channel_name", sort=True)
            },
            "source_parent_context_counts": source["parent_context_status"].value_counts().to_dict(),
            "source_video_context_counts": source["video_context_status"].value_counts().to_dict(),
            "representative": validation,
            "representative_script_counts": representative_template["script_category"].value_counts().sort_index().to_dict(),
            "demand_enriched_script_counts": enriched_template["script_category"].value_counts().sort_index().to_dict(),
            "demand_enriched_selection_methods": enriched_manifest["selection_source"].value_counts().to_dict(),
            "remaining_after_representative_rows": len(remaining),
        },
    )
    (output / "experiment_2a_methodology.md").write_text(
        _render_methodology(
            source,
            representative_template,
            representative_manifest,
            enriched_template,
            enriched_manifest,
            validation,
            seed,
        ),
        encoding="utf-8",
    )
    return {
        "output_dir": str(output),
        "validation": validation,
        "selection_methods": enriched_manifest["selection_source"].value_counts().to_dict(),
        "parent_context_counts": source["parent_context_status"].value_counts().to_dict(),
        "script_counts": source["script_category"].value_counts().sort_index().to_dict(),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comments", type=Path, default=DEFAULT_PILOT_COMMENTS)
    parser.add_argument("--videos", type=Path, default=DEFAULT_PILOT_VIDEOS)
    parser.add_argument("--preprocessed", type=Path, default=DEFAULT_PREPROCESSED)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--seed", type=int, default=EXPERIMENT_2A_SEED)
    parser.add_argument("--per-channel", type=int, default=REPRESENTATIVE_PER_CHANNEL)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = prepare(
        comments_path=args.comments,
        videos_path=args.videos,
        preprocessed_path=args.preprocessed,
        output_dir=args.output_dir,
        seed=args.seed,
        per_channel=args.per_channel,
    )
    validation = result["validation"]
    print(f"Source comments: {validation['source_rows']}; videos: {validation['source_unique_videos']}")
    print(f"Representative rows: {validation['representative_rows']}; channels: {validation['representative_channel_counts']}")
    print(f"Demand-enriched rows: {validation['demand_enriched_rows']}; methods: {result['selection_methods']}")
    print(f"Outputs: {result['output_dir']}")


if __name__ == "__main__":
    main()
