"""Versioned annotation contract for Component 2 feasibility datasets."""

from __future__ import annotations

import hashlib
import unicodedata
from typing import Iterable

import pandas as pd


ANNOTATION_SCHEMA_VERSION = "component2.audience-demand.v1"
TEXT_PROVENANCE_VERSION = "component2.comment-text.v1"
EVIDENCE_TEXT_FIELD = "raw_comment_text"

PRIMARY_SIGNALS = (
    "EXPLICIT_CONTENT_REQUEST",
    "CONTENT_CHANGE_PREFERENCE",
    "INFORMATION_NEED",
    "CONTENT_QUALITY_FEEDBACK",
    "TOPICAL_INTEREST_OR_DISCUSSION",
    "ORDINARY_REACTION",
    "SPAM_OR_IRRELEVANT",
    "UNCLEAR",
)
ACTIONABILITY_LABELS = ("YES", "NO", "UNCLEAR")
SPAM_STATUS_LABELS = ("SPAM", "NOT_SPAM", "UNCLEAR")
ANNOTATOR_STATUSES = ("NOT_STARTED", "IN_PROGRESS", "COMPLETE", "NEEDS_REVIEW")
ADJUDICATION_STATUSES = ("NOT_STARTED", "PENDING", "ADJUDICATED")

TEXT_PROVENANCE_FIELDS = [
    "annotation_schema_version",
    "text_provenance_version",
    "raw_comment_text",
    "raw_comment_text_sha256",
    "normalized_text",
    "cleaned_text",
    "evidence_text_field",
]


def _annotator_fields(prefix: str) -> list[str]:
    return [
        f"{prefix}_id",
        f"{prefix}_status",
        f"{prefix}_primary_signal",
        f"{prefix}_secondary_signals",
        f"{prefix}_actionable_content_demand",
        f"{prefix}_requested_action",
        f"{prefix}_requested_topic",
        f"{prefix}_requested_format",
        f"{prefix}_request_target",
        f"{prefix}_evidence_span",
        f"{prefix}_notes",
        f"{prefix}_spam_status",
        f"{prefix}_completed_at_utc",
    ]


REVIEW_ANNOTATION_FIELDS = [
    *_annotator_fields("annotator_1"),
    *_annotator_fields("annotator_2"),
    "adjudication_status",
    "adjudicator_id",
    "adjudicated_at_utc",
    "final_primary_signal",
    "final_secondary_signals",
    "final_actionable_content_demand",
    "final_requested_action",
    "final_requested_topic",
    "final_requested_format",
    "final_request_target",
    "final_evidence_span",
    "final_notes",
    "final_spam_status",
    "spam_notes",
]


def raw_text_sha256(value: object) -> str:
    """Hash the exact UTF-8 representation of one decoded source text field."""

    text = "" if value is None or pd.isna(value) else str(value)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalized_text(value: object) -> str:
    """Return the explicit NFC processing representation of source text."""

    text = "" if value is None or pd.isna(value) else str(value)
    return unicodedata.normalize("NFC", text)


def _invalid_values(series: pd.Series, allowed: Iterable[str]) -> list[str]:
    values = series.astype("string").fillna("").str.strip()
    return sorted(set(values[values.ne("")]).difference(allowed))


def _secondary_tokens(series: pd.Series) -> set[str]:
    tokens: set[str] = set()
    for value in series.astype("string").fillna(""):
        tokens.update(part.strip() for part in value.split(";") if part.strip())
    return tokens


def validate_annotation_frame(frame: pd.DataFrame) -> None:
    """Validate schema, labels, and raw/normalized text provenance.

    Blank human fields are valid because preparation outputs are annotation
    templates. This validator never infers or migrates a human label.
    """

    required = {
        "comment_id",
        *TEXT_PROVENANCE_FIELDS,
        *REVIEW_ANNOTATION_FIELDS,
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Canonical annotation frame is missing columns: {missing}")
    if frame["comment_id"].astype("string").fillna("").str.strip().eq("").any():
        raise ValueError("Canonical annotation frame contains an empty comment ID")
    if frame["comment_id"].astype(str).duplicated().any():
        raise ValueError("Canonical annotation frame contains duplicate comment IDs")

    versions = set(
        frame["annotation_schema_version"].astype("string").fillna("").str.strip()
    )
    if versions != {ANNOTATION_SCHEMA_VERSION}:
        raise ValueError(f"Unexpected annotation schema versions: {sorted(versions)}")
    provenance_versions = set(
        frame["text_provenance_version"].astype("string").fillna("").str.strip()
    )
    if provenance_versions != {TEXT_PROVENANCE_VERSION}:
        raise ValueError(
            f"Unexpected text provenance versions: {sorted(provenance_versions)}"
        )
    if not frame["evidence_text_field"].eq(EVIDENCE_TEXT_FIELD).all():
        raise ValueError("Evidence spans must refer to raw_comment_text")

    expected_normalized = frame["raw_comment_text"].map(normalized_text)
    actual_normalized = frame["normalized_text"].fillna("").astype(str)
    if not actual_normalized.eq(expected_normalized).all():
        raise ValueError("normalized_text is not NFC-normalized raw_comment_text")
    expected_hashes = frame["raw_comment_text"].map(raw_text_sha256)
    if not frame["raw_comment_text_sha256"].astype(str).eq(expected_hashes).all():
        raise ValueError("raw_comment_text_sha256 does not match raw_comment_text")

    for prefix in ("annotator_1", "annotator_2", "final"):
        invalid_primary = _invalid_values(
            frame[f"{prefix}_primary_signal"], PRIMARY_SIGNALS
        )
        invalid_actionability = _invalid_values(
            frame[f"{prefix}_actionable_content_demand"], ACTIONABILITY_LABELS
        )
        invalid_spam = _invalid_values(
            frame[f"{prefix}_spam_status"], SPAM_STATUS_LABELS
        )
        invalid_secondary = sorted(
            _secondary_tokens(frame[f"{prefix}_secondary_signals"])
            .difference(PRIMARY_SIGNALS)
        )
        if invalid_primary:
            raise ValueError(f"Invalid {prefix} primary signals: {invalid_primary}")
        if invalid_actionability:
            raise ValueError(
                f"Invalid {prefix} actionability labels: {invalid_actionability}"
            )
        if invalid_spam:
            raise ValueError(f"Invalid {prefix} spam labels: {invalid_spam}")
        if invalid_secondary:
            raise ValueError(f"Invalid {prefix} secondary signals: {invalid_secondary}")

    for prefix in ("annotator_1", "annotator_2"):
        invalid_statuses = _invalid_values(
            frame[f"{prefix}_status"], ANNOTATOR_STATUSES
        )
        if invalid_statuses:
            raise ValueError(f"Invalid {prefix} statuses: {invalid_statuses}")
        completed = frame[f"{prefix}_status"].eq("COMPLETE")
        if completed.any():
            required_labels = frame.loc[
                completed,
                [f"{prefix}_primary_signal", f"{prefix}_actionable_content_demand"],
            ]
            if required_labels.fillna("").astype(str).apply(
                lambda column: column.str.strip().eq("")
            ).any().any():
                raise ValueError(f"{prefix} COMPLETE rows require both core labels")

    invalid_adjudication = _invalid_values(
        frame["adjudication_status"], ADJUDICATION_STATUSES
    )
    if invalid_adjudication:
        raise ValueError(f"Invalid adjudication statuses: {invalid_adjudication}")
