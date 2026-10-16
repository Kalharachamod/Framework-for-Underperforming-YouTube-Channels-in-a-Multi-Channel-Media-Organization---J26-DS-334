"""Validation rules for demand and spam annotation responses."""

from __future__ import annotations

from dataclasses import dataclass

from research.component_2.src.annotation import DEMAND_SUBTYPES, LABEL_VALUES, SPAM_STATUS_VALUES


@dataclass(frozen=True)
class AnnotationResponse:
    demand_label: str
    spam_status: str
    demand_subtype: str = ""
    annotation_notes: str = ""
    spam_notes: str = ""
    is_submitted: bool = False


def validate_response(
    demand_label: str,
    spam_status: str,
    demand_subtype: str = "",
    annotation_notes: str = "",
    spam_notes: str = "",
    is_submitted: bool = False,
) -> AnnotationResponse:
    demand_label = demand_label.strip().upper()
    spam_status = spam_status.strip().upper()
    demand_subtype = demand_subtype.strip()

    if demand_label not in LABEL_VALUES:
        raise ValueError(f"Invalid demand label: {demand_label}")
    if spam_status not in SPAM_STATUS_VALUES:
        raise ValueError(f"Invalid spam status: {spam_status}")
    if demand_label == "DEMAND" and demand_subtype not in DEMAND_SUBTYPES:
        raise ValueError("Demand subtype is required when demand label is DEMAND")
    if demand_label != "DEMAND" and demand_subtype:
        raise ValueError("Demand subtype must be blank unless demand label is DEMAND")

    return AnnotationResponse(
        demand_label=demand_label,
        spam_status=spam_status,
        demand_subtype=demand_subtype,
        annotation_notes=annotation_notes,
        spam_notes=spam_notes,
        is_submitted=is_submitted,
    )
