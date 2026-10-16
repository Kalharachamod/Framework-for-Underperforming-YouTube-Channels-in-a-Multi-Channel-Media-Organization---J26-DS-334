"""Export helpers for annotation responses."""

from __future__ import annotations

import pandas as pd

from .auth import AuthenticatedAnnotator


def export_for_researcher(store, requester: AuthenticatedAnnotator) -> pd.DataFrame:
    if not requester.is_admin:
        raise PermissionError("Only explicitly authorized researcher admins may export responses")
    frame = store.export_responses()
    expected_columns = [
        "participant_id",
        "display_name",
        "section_id",
        "section_label",
        "assignment_template_id",
        "batch_name",
        "position",
        "comment_id",
        "demand_label",
        "spam_status",
        "demand_subtype",
        "annotation_notes",
        "spam_notes",
        "is_submitted",
        "created_at",
        "updated_at",
    ]
    for column in expected_columns:
        if column not in frame.columns:
            frame[column] = ""
    return frame[expected_columns]
