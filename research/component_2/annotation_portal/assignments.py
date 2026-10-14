"""Deterministic annotation assignment generation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import pandas as pd

from .auth import development_tokens, hash_invitation_token


PRIMARY_ANNOTATOR_ID = "primary_annotator"
VOLUNTEER_ANNOTATOR_IDS = [f"volunteer_{index}" for index in range(1, 6)]
ADMIN_ANNOTATOR_ID = "researcher_admin"
DEFAULT_VOLUNTEER_COUNT = 5
DEFAULT_VOLUNTEER_ASSIGNMENT_SIZE = 30
PRIMARY_SECTION_ID = "primary_researcher"
SECTION_IDS = [f"section_{letter}" for letter in "abcde"]
SECTION_TEMPLATE_BY_ID = {section_id: annotator_id for section_id, annotator_id in zip(SECTION_IDS, VOLUNTEER_ANNOTATOR_IDS)}
SECTION_TEMPLATE_BY_ID[PRIMARY_SECTION_ID] = PRIMARY_ANNOTATOR_ID
SECTION_LABEL_BY_ID = {
    "section_a": "Section A",
    "section_b": "Section B",
    "section_c": "Section C",
    "section_d": "Section D",
    "section_e": "Section E",
    PRIMARY_SECTION_ID: "Primary researcher mode",
}


@dataclass(frozen=True)
class AnnotatorRecord:
    annotator_id: str
    display_name: str
    role: str
    token_hash: str
    active: bool
    assigned_count: int


@dataclass(frozen=True)
class SectionOption:
    section_id: str
    label: str
    assignment_template_id: str
    assigned_count: int


def stable_assignment_hash(value: object, seed: int, salt: str = "") -> str:
    return hashlib.md5(f"{seed}:{salt}:{value}".encode("utf-8")).hexdigest()


def section_options() -> list[SectionOption]:
    options = [
        SectionOption(
            section_id=section_id,
            label=SECTION_LABEL_BY_ID[section_id],
            assignment_template_id=SECTION_TEMPLATE_BY_ID[section_id],
            assigned_count=DEFAULT_VOLUNTEER_ASSIGNMENT_SIZE,
        )
        for section_id in SECTION_IDS
    ]
    options.append(
        SectionOption(
            section_id=PRIMARY_SECTION_ID,
            label=SECTION_LABEL_BY_ID[PRIMARY_SECTION_ID],
            assignment_template_id=PRIMARY_ANNOTATOR_ID,
            assigned_count=300,
        )
    )
    return options


def section_option(section_id: str) -> SectionOption:
    for option in section_options():
        if option.section_id == section_id:
            return option
    raise ValueError(f"Unknown annotation section: {section_id}")


def load_annotation_comments(path) -> pd.DataFrame:
    return pd.read_csv(path, dtype="string").fillna("")


def create_development_annotators(secret: str) -> list[AnnotatorRecord]:
    tokens = development_tokens()
    records = [
        AnnotatorRecord(
            annotator_id=PRIMARY_ANNOTATOR_ID,
            display_name="Primary annotator",
            role="primary",
            token_hash=hash_invitation_token(tokens[PRIMARY_ANNOTATOR_ID], secret),
            active=True,
            assigned_count=300,
        )
    ]
    for index, annotator_id in enumerate(VOLUNTEER_ANNOTATOR_IDS, start=1):
        records.append(
            AnnotatorRecord(
                annotator_id=annotator_id,
                display_name=f"Volunteer {index}",
                role="volunteer",
                token_hash=hash_invitation_token(tokens[annotator_id], secret),
                active=True,
                assigned_count=DEFAULT_VOLUNTEER_ASSIGNMENT_SIZE,
            )
        )
    records.append(
        AnnotatorRecord(
            annotator_id=ADMIN_ANNOTATOR_ID,
            display_name="Researcher admin",
            role="researcher_admin",
            token_hash=hash_invitation_token(tokens[ADMIN_ANNOTATOR_ID], secret),
            active=True,
            assigned_count=0,
        )
    )
    return records


def generate_assignments(
    comments: pd.DataFrame,
    seed: int,
    volunteer_ids: list[str] | None = None,
    volunteer_assignment_size: int = DEFAULT_VOLUNTEER_ASSIGNMENT_SIZE,
) -> pd.DataFrame:
    required = {"comment_id", "channel_id", "script_category"}
    missing = required.difference(comments.columns)
    if missing:
        raise ValueError(f"Cannot generate assignments without columns: {sorted(missing)}")

    volunteer_ids = volunteer_ids or VOLUNTEER_ANNOTATOR_IDS
    comments = comments.copy().reset_index(drop=True)
    comments["_source_order"] = range(len(comments))

    primary = pd.DataFrame(
        {
            "annotator_id": PRIMARY_ANNOTATOR_ID,
            "comment_id": comments["comment_id"],
            "batch_name": "primary_all",
            "position": comments["_source_order"] + 1,
        }
    )

    volunteer_frames: list[pd.DataFrame] = []
    selected_comment_ids: set[str] = set()
    channels = sorted(comments["channel_id"].dropna().unique())
    per_channel = volunteer_assignment_size // len(channels)
    remainder = volunteer_assignment_size % len(channels)

    for volunteer_index, annotator_id in enumerate(volunteer_ids):
        assigned_rows = []
        for channel_index, channel_id in enumerate(channels):
            quota = per_channel + (1 if channel_index < remainder else 0)
            channel_pool = comments[
                (comments["channel_id"] == channel_id)
                & (~comments["comment_id"].isin(selected_comment_ids))
            ].copy()
            selected = _select_balanced_by_script(
                channel_pool,
                quota,
                seed=seed,
                salt=f"{annotator_id}:{channel_id}:{volunteer_index}",
            )
            assigned_rows.append(selected)
            selected_comment_ids.update(selected["comment_id"].astype(str))

        volunteer_comments = pd.concat(assigned_rows, ignore_index=True)
        if len(volunteer_comments) != volunteer_assignment_size:
            raise ValueError(
                f"{annotator_id} received {len(volunteer_comments)} comments, "
                f"expected {volunteer_assignment_size}"
            )
        volunteer_comments = volunteer_comments.sort_values(["channel_id", "_assignment_hash", "comment_id"])
        volunteer_frames.append(
            pd.DataFrame(
                {
                    "annotator_id": annotator_id,
                    "comment_id": volunteer_comments["comment_id"].tolist(),
                    "batch_name": f"volunteer_{volunteer_index + 1}",
                    "position": range(1, len(volunteer_comments) + 1),
                }
            )
        )

    return pd.concat([primary, *volunteer_frames], ignore_index=True)


def assignment_distribution(comments: pd.DataFrame, assignments: pd.DataFrame) -> pd.DataFrame:
    merged = assignments.merge(
        comments[["comment_id", "channel_name", "channel_id", "script_category"]],
        on="comment_id",
        how="left",
    )
    return (
        merged.groupby(["annotator_id", "channel_name", "script_category"], dropna=False)
        .agg(comments=("comment_id", "count"))
        .reset_index()
        .sort_values(["annotator_id", "channel_name", "script_category"])
    )


def _select_balanced_by_script(frame: pd.DataFrame, count: int, seed: int, salt: str) -> pd.DataFrame:
    if count <= 0:
        return frame.iloc[0:0].copy()
    if len(frame) < count:
        raise ValueError(f"Not enough comments available to select {count} rows")

    working = frame.copy()
    working["_assignment_hash"] = working["comment_id"].map(
        lambda value: stable_assignment_hash(value, seed=seed, salt=salt)
    )
    categories = (
        working.groupby("script_category", dropna=False)["comment_id"]
        .count()
        .sort_values(ascending=False)
        .index.tolist()
    )
    pools = {
        category: group.sort_values(["_assignment_hash", "comment_id"]).to_dict("records")
        for category, group in working.groupby("script_category", dropna=False)
    }
    selected: list[dict] = []
    while len(selected) < count:
        progressed = False
        for category in categories:
            pool = pools.get(category, [])
            if pool:
                selected.append(pool.pop(0))
                progressed = True
                if len(selected) == count:
                    break
        if not progressed:
            break
    return pd.DataFrame(selected)
