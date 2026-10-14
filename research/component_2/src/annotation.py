"""Audience-demand annotation sampling and template creation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


BASE_ANNOTATION_COLUMNS = [
    "comment_id",
    "channel_name",
    "video_id",
    "video_title",
    "video_description",
    "video_url",
    "parent_comment_text",
    "channel_id",
    "published_at",
    "is_reply",
    "original_text",
    "cleaned_text",
    "script_category",
    "preprocessing_flags",
    "sampling_stratum",
]

DEMAND_ANNOTATION_COLUMNS = [
    "primary_label",
    "demand_subtype",
    "annotation_notes",
    "annotator_1_label",
    "annotator_2_label",
    "final_adjudicated_label",
]

SPAM_ANNOTATION_COLUMNS = [
    "annotator_1_spam_status",
    "annotator_2_spam_status",
    "final_spam_status",
    "spam_notes",
]

ANNOTATION_COLUMNS = BASE_ANNOTATION_COLUMNS + DEMAND_ANNOTATION_COLUMNS + SPAM_ANNOTATION_COLUMNS
HUMAN_ANNOTATION_COLUMNS = DEMAND_ANNOTATION_COLUMNS + SPAM_ANNOTATION_COLUMNS
VIDEO_CONTEXT_COLUMNS = ["video_title", "video_description", "video_url", "parent_comment_text"]

LABEL_VALUES = ["DEMAND", "NON_DEMAND", "UNCLEAR"]
SPAM_STATUS_VALUES = ["SPAM", "NOT_SPAM", "UNCLEAR"]

DEMAND_SUBTYPES = [
    "new_topic_content_request",
    "follow_up_or_additional_explanation",
    "content_format_preference",
    "language_preference",
    "content_improvement_request",
    "other_content_need",
]


@dataclass(frozen=True)
class AnnotationSamplingConfig:
    sample_size: int = 300
    random_seed: int = 334
    per_channel_target: int | None = None
    minority_target_per_channel: int = 8


def stable_hash(value: object, seed: int = 334) -> str:
    return hashlib.md5(f"{seed}:{value}".encode("utf-8")).hexdigest()


def assign_script_category(row: pd.Series) -> str:
    has_sinhala = bool(row.get("has_sinhala", False))
    has_latin = bool(row.get("has_latin", False))
    emoji_only = bool(row.get("emoji_only", False))
    if emoji_only:
        return "emoji_only"
    if has_sinhala and has_latin:
        return "mixed_sinhala_latin"
    if has_sinhala:
        return "sinhala_script"
    if has_latin:
        return "latin_script"
    return "other_or_symbolic"


def combine_preprocessing_flags(row: pd.Series) -> str:
    flags: list[str] = []
    review_reasons = row.get("review_reasons", "")
    if pd.notna(review_reasons) and str(review_reasons).strip():
        flags.extend(part for part in str(review_reasons).split(";") if part)
    if bool(row.get("repeated_cleaned_text", False)) and "repeated_cleaned_text" not in flags:
        flags.append("repeated_cleaned_text")
    if bool(row.get("exclude_from_modeling", False)) and "exclude_from_modeling" not in flags:
        flags.append("exclude_from_modeling")
    return ";".join(sorted(set(flags)))


def prepare_annotation_source(
    preprocessed_comments: pd.DataFrame,
    validated_comments: pd.DataFrame,
) -> pd.DataFrame:
    metadata = validated_comments[
        ["comment_id", "channel_name", "parent_comment_id", "published_at"]
    ].copy()
    source = preprocessed_comments.merge(metadata, on="comment_id", how="left")
    source["script_category"] = source.apply(assign_script_category, axis=1)
    source["preprocessing_flags"] = source.apply(combine_preprocessing_flags, axis=1)
    source["is_reply"] = source["parent_comment_id"].notna() & (
        source["parent_comment_id"].astype(str).str.strip() != ""
    )
    source["published_at"] = pd.to_datetime(source["published_at"], utc=True, errors="coerce")
    return source


def assign_sampling_stratum(row: pd.Series) -> str:
    if row["script_category"] == "mixed_sinhala_latin":
        return "mixed_sinhala_latin"
    if row["script_category"] == "emoji_only":
        return "emoji_only"
    if bool(row.get("is_reply", False)):
        return "reply"
    if int(row.get("char_length", 0)) < 5:
        return "very_short"
    if row["script_category"] == "sinhala_script":
        return "sinhala_script"
    if row["script_category"] == "latin_script":
        return "latin_script"
    return "other"


def _take_deterministic(
    frame: pd.DataFrame,
    count: int,
    seed: int,
    already_selected: set[str],
) -> pd.DataFrame:
    if count <= 0 or frame.empty:
        return frame.iloc[0:0].copy()
    candidates = frame[~frame["comment_id"].isin(already_selected)].copy()
    if candidates.empty:
        return candidates
    candidates["_sample_hash"] = candidates["comment_id"].map(lambda value: stable_hash(value, seed))
    return candidates.sort_values(["_sample_hash", "comment_id"]).head(count).drop(columns=["_sample_hash"])


def create_annotation_sample(
    source: pd.DataFrame,
    config: AnnotationSamplingConfig | None = None,
) -> pd.DataFrame:
    config = config or AnnotationSamplingConfig()
    if source.empty:
        raise ValueError("Cannot sample from an empty annotation source")

    working = source.copy()
    if "script_category" not in working.columns:
        working["script_category"] = working.apply(assign_script_category, axis=1)
    if "is_reply" not in working.columns:
        working["is_reply"] = False
    working["sampling_stratum"] = working.apply(assign_sampling_stratum, axis=1)
    channels = sorted(working["channel_id"].dropna().unique())
    if not channels:
        raise ValueError("Annotation source has no channel_id values")

    per_channel = config.per_channel_target or config.sample_size // len(channels)
    selected_frames: list[pd.DataFrame] = []
    selected_ids: set[str] = set()
    priority_strata = [
        "mixed_sinhala_latin",
        "emoji_only",
        "reply",
        "very_short",
        "sinhala_script",
        "latin_script",
    ]

    for channel_id in channels:
        channel_frame = working[working["channel_id"] == channel_id]
        channel_selected = 0
        for stratum in priority_strata:
            picked = _take_deterministic(
                channel_frame[channel_frame["sampling_stratum"] == stratum],
                config.minority_target_per_channel,
                config.random_seed,
                selected_ids,
            )
            if not picked.empty:
                selected_frames.append(picked)
                ids = set(picked["comment_id"].astype(str))
                selected_ids.update(ids)
                channel_selected += len(picked)
        remaining = per_channel - channel_selected
        if remaining > 0:
            picked = _take_deterministic(
                channel_frame,
                remaining,
                config.random_seed,
                selected_ids,
            )
            if not picked.empty:
                selected_frames.append(picked)
                selected_ids.update(set(picked["comment_id"].astype(str)))

    sample = pd.concat(selected_frames, ignore_index=True) if selected_frames else working.iloc[0:0].copy()
    if len(sample) < config.sample_size:
        fill = _take_deterministic(working, config.sample_size - len(sample), config.random_seed, selected_ids)
        sample = pd.concat([sample, fill], ignore_index=True)
    elif len(sample) > config.sample_size:
        sample["_sample_hash"] = sample["comment_id"].map(lambda value: stable_hash(value, config.random_seed))
        sample = sample.sort_values(["channel_id", "_sample_hash", "comment_id"]).groupby("channel_id", group_keys=False).head(per_channel)
        if len(sample) > config.sample_size:
            sample = sample.sort_values(["_sample_hash", "comment_id"]).head(config.sample_size)
        sample = sample.drop(columns=[col for col in ["_sample_hash"] if col in sample.columns])

    sample = sample.drop_duplicates("comment_id").copy()
    sample["_sample_hash"] = sample["comment_id"].map(lambda value: stable_hash(value, config.random_seed))
    sample = sample.sort_values(["channel_id", "_sample_hash", "comment_id"]).drop(columns=["_sample_hash"])
    return sample.reset_index(drop=True)


def create_annotation_template(sample: pd.DataFrame) -> pd.DataFrame:
    template = sample.copy()
    for column in HUMAN_ANNOTATION_COLUMNS:
        template[column] = ""
    for column in ANNOTATION_COLUMNS:
        if column not in template.columns:
            template[column] = ""
    return template[ANNOTATION_COLUMNS]


def add_spam_annotation_fields(template: pd.DataFrame) -> pd.DataFrame:
    updated = template.copy()
    for column in SPAM_ANNOTATION_COLUMNS:
        if column not in updated.columns:
            updated[column] = ""
    for column in ANNOTATION_COLUMNS:
        if column not in updated.columns:
            updated[column] = ""
    extra_columns = [column for column in updated.columns if column not in ANNOTATION_COLUMNS]
    return updated[ANNOTATION_COLUMNS + extra_columns]


def spreadsheet_safe_text(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{text}"
    return text


def add_video_context_fields(
    template: pd.DataFrame,
    videos: pd.DataFrame,
    comments: pd.DataFrame | None = None,
) -> pd.DataFrame:
    updated = template.drop(columns=[col for col in VIDEO_CONTEXT_COLUMNS if col in template.columns]).copy()
    updated["video_id"] = updated["video_id"].astype("string")

    video_metadata = videos[["video_id", "title", "description"]].drop_duplicates("video_id").rename(
        columns={"title": "video_title", "description": "video_description"}
    )
    video_metadata["video_id"] = video_metadata["video_id"].astype("string")
    video_metadata["video_title"] = video_metadata["video_title"].map(spreadsheet_safe_text)
    video_metadata["video_description"] = video_metadata["video_description"].map(spreadsheet_safe_text)

    updated = updated.merge(video_metadata, on="video_id", how="left", sort=False)
    updated["video_title"] = updated["video_title"].fillna("")
    updated["video_description"] = updated["video_description"].fillna("")
    updated["video_url"] = updated["video_id"].fillna("").astype(str).map(
        lambda video_id: f"https://www.youtube.com/watch?v={video_id}" if video_id else ""
    )

    updated["parent_comment_text"] = ""
    if comments is not None and {"comment_id", "comment_text", "parent_comment_id"}.issubset(comments.columns):
        comments_lookup = comments[["comment_id", "comment_text", "parent_comment_id"]].copy()
        comments_lookup["comment_id"] = comments_lookup["comment_id"].astype(str)
        parent_by_comment = comments_lookup.set_index("comment_id")["parent_comment_id"].to_dict()
        text_by_comment = comments_lookup.set_index("comment_id")["comment_text"].to_dict()

        parent_ids = updated["comment_id"].astype(str).map(parent_by_comment).fillna("")
        updated["parent_comment_text"] = parent_ids.map(text_by_comment).fillna("").map(spreadsheet_safe_text)

    for column in ANNOTATION_COLUMNS:
        if column not in updated.columns:
            updated[column] = ""
    extra_columns = [column for column in updated.columns if column not in ANNOTATION_COLUMNS]
    return updated[ANNOTATION_COLUMNS + extra_columns]


def nonblank_annotation_counts(
    template: pd.DataFrame,
    columns: list[str] | None = None,
) -> dict[str, int]:
    checked_columns = columns or HUMAN_ANNOTATION_COLUMNS
    counts: dict[str, int] = {}
    for column in checked_columns:
        if column in template.columns:
            counts[column] = int(template[column].fillna("").astype(str).str.strip().ne("").sum())
    return counts


def ensure_no_human_annotations(template: pd.DataFrame) -> None:
    nonblank = {
        column: count
        for column, count in nonblank_annotation_counts(template).items()
        if count > 0
    }
    if nonblank:
        raise ValueError(
            "Existing annotation CSV contains human annotations and must not be overwritten: "
            f"{nonblank}"
        )


def validate_existing_annotation_template(
    existing_template: pd.DataFrame,
    expected_template: pd.DataFrame,
) -> None:
    if len(existing_template) != len(expected_template):
        raise ValueError(
            "Existing annotation CSV row count does not match the deterministic sample: "
            f"{len(existing_template)} != {len(expected_template)}"
        )
    if existing_template["comment_id"].astype(str).tolist() != expected_template["comment_id"].astype(str).tolist():
        raise ValueError("Existing annotation CSV comment_id order differs from the deterministic sample")

    preserved_columns = [
        "comment_id",
        "channel_id",
        "channel_name",
        "video_id",
        "original_text",
        "cleaned_text",
        "script_category",
        "preprocessing_flags",
        "sampling_stratum",
    ]
    changed_columns: list[str] = []
    for column in preserved_columns:
        if column not in existing_template.columns or column not in expected_template.columns:
            changed_columns.append(column)
            continue
        existing_values = existing_template[column].fillna("").astype(str).tolist()
        expected_values = expected_template[column].fillna("").astype(str).tolist()
        if existing_values != expected_values:
            changed_columns.append(column)
    if changed_columns:
        raise ValueError(
            "Existing annotation CSV differs from the deterministic sample in preserved columns: "
            f"{changed_columns}"
        )


def annotation_distribution_summary(template: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "by_channel": template.groupby(["channel_id", "channel_name"], dropna=False)
        .agg(comments=("comment_id", "count"), videos=("video_id", "nunique"))
        .reset_index()
        .sort_values("comments", ascending=False),
        "by_script_category": template["script_category"].value_counts().rename_axis("script_category").reset_index(name="count"),
        "by_sampling_stratum": template["sampling_stratum"].value_counts().rename_axis("sampling_stratum").reset_index(name="count"),
        "by_reply_status": template["is_reply"].value_counts().rename_axis("is_reply").reset_index(name="count"),
    }


def write_annotation_outputs(
    template: pd.DataFrame,
    output_dir: str | Path,
) -> dict[str, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    annotation_csv = output_path / "component2_demand_annotation_sample.csv"
    template.to_csv(annotation_csv, index=False)
    summaries = annotation_distribution_summary(template)
    paths = {"annotation_csv": annotation_csv}
    for name, frame in summaries.items():
        path = output_path / f"{name}.csv"
        frame.to_csv(path, index=False)
        paths[name] = path
    return paths
