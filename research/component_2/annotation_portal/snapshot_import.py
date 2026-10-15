"""Validate and import the reviewed 300-comment annotation snapshot."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .assignments import (
    PRIMARY_ANNOTATOR_ID,
    SECTION_TEMPLATE_BY_ID,
    VOLUNTEER_ANNOTATOR_IDS,
    generate_assignments,
)


REQUIRED_SNAPSHOT_COLUMNS = {
    "comment_id",
    "channel_id",
    "channel_name",
    "video_id",
    "video_title",
    "video_description",
    "video_url",
    "original_text",
    "cleaned_text",
    "script_category",
}


@dataclass(frozen=True)
class SnapshotValidation:
    comments: pd.DataFrame
    assignments: pd.DataFrame
    invalid_records: int
    errors: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class ImportReport:
    inserted: int
    updated: int
    skipped: int
    invalid: int


class SnapshotValidationError(ValueError):
    """Raised when the reviewed snapshot cannot be safely imported."""

    def __init__(self, validation: SnapshotValidation):
        self.validation = validation
        super().__init__("; ".join(validation.errors))


def load_and_validate_snapshot(path: str | Path, seed: int) -> SnapshotValidation:
    path = Path(path)
    errors: list[str] = []
    invalid_records = 0
    try:
        comments = pd.read_csv(path, dtype="string").fillna("")
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        return SnapshotValidation(pd.DataFrame(), pd.DataFrame(), 1, (f"Could not read snapshot: {exc}",))

    missing = REQUIRED_SNAPSHOT_COLUMNS.difference(comments.columns)
    if missing:
        errors.append(f"Missing required snapshot columns: {sorted(missing)}")
    if len(comments) != 300:
        errors.append(f"Snapshot must contain exactly 300 rows; found {len(comments)}")
    if "comment_id" in comments.columns:
        empty_ids = int(comments["comment_id"].astype(str).str.strip().eq("").sum())
        duplicate_ids = int(comments["comment_id"].duplicated().sum())
        invalid_records += empty_ids + duplicate_ids
        if empty_ids:
            errors.append(f"Snapshot contains {empty_ids} empty comment IDs")
        if duplicate_ids:
            errors.append(f"Snapshot contains {duplicate_ids} duplicate comment IDs")
    if "channel_id" in comments.columns and comments["channel_id"].nunique() != 5:
        errors.append("Snapshot must contain exactly five channels for Sections A-E")

    assignments = pd.DataFrame()
    if not missing and len(comments) == 300:
        try:
            assignments = generate_assignments(comments, seed=seed)
            errors.extend(_assignment_errors(comments, assignments))
        except ValueError as exc:
            errors.append(f"Could not regenerate deterministic assignments: {exc}")

    return SnapshotValidation(comments, assignments, invalid_records, tuple(errors))


def import_snapshot(store, path: str | Path, seed: int, source_name: str | None = None) -> ImportReport:
    validation = load_and_validate_snapshot(path, seed)
    if not validation.is_valid:
        raise SnapshotValidationError(validation)
    result = store.import_snapshot(
        validation.comments,
        validation.assignments,
        assignment_seed=seed,
        source_name=source_name or Path(path).name,
    )
    return ImportReport(
        inserted=int(result.get("inserted", 0)),
        updated=int(result.get("updated", 0)),
        skipped=int(result.get("skipped", 0)),
        invalid=int(result.get("invalid", validation.invalid_records)),
    )


def _assignment_errors(comments: pd.DataFrame, assignments: pd.DataFrame) -> list[str]:
    errors: list[str] = []
    primary = assignments[assignments["annotator_id"] == PRIMARY_ANNOTATOR_ID]
    if len(primary) != 300:
        errors.append(f"Primary assignment must contain 300 comments; found {len(primary)}")

    merged = assignments.merge(comments[["comment_id", "channel_id"]], on="comment_id", how="left")
    volunteer_sets: list[set[str]] = []
    for annotator_id in VOLUNTEER_ANNOTATOR_IDS:
        selected = merged[merged["annotator_id"] == annotator_id]
        if len(selected) != 30:
            errors.append(f"{annotator_id} assignment must contain 30 comments; found {len(selected)}")
        per_channel = selected.groupby("channel_id").size()
        if set(per_channel.tolist()) != {6} or len(per_channel) != 5:
            errors.append(f"{annotator_id} assignment must contain six comments from each channel")
        volunteer_sets.append(set(selected["comment_id"].astype(str)))

    combined: set[str] = set()
    for selected_ids in volunteer_sets:
        if combined.intersection(selected_ids):
            errors.append("Volunteer section assignments overlap")
        combined.update(selected_ids)
    if len(combined) != 150:
        errors.append(f"Five volunteer sections must contain 150 unique comments; found {len(combined)}")
    if not combined.issubset(set(primary["comment_id"].astype(str))):
        errors.append("Volunteer section comments must be a subset of the primary 300 comments")

    expected_templates = set(SECTION_TEMPLATE_BY_ID.values())
    if set(assignments["annotator_id"]) != expected_templates:
        errors.append("Assignment templates do not match the five sections and primary mode")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate or import the Component 2 annotation snapshot",
        epilog=(
            "This command intentionally accepts snapshot arguments only. The run ID and database "
            "connection are read from environment configuration; --host and --password-prompt "
            "belong to connection-audit tools, not this importer."
        ),
    )
    parser.add_argument("--csv", type=Path, required=True, help="Reviewed 300-comment CSV snapshot")
    parser.add_argument("--seed", type=int, default=20261014)
    parser.add_argument("--source-name", default=None)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)

    validation = load_and_validate_snapshot(args.csv, args.seed)
    if not validation.is_valid:
        print(
            json.dumps(
                {"inserted": 0, "updated": 0, "skipped": 0, "invalid": validation.invalid_records, "errors": validation.errors},
                ensure_ascii=False,
            )
        )
        return 2
    if args.validate_only:
        print(json.dumps({"inserted": 0, "updated": 0, "skipped": len(validation.comments), "invalid": 0}))
        return 0

    from .config import load_config
    from .supabase_store import SupabaseAnnotationStore

    config = load_config(require_app_db_url=False)
    if config.mode != "supabase" or not config.supabase_import_db_url:
        parser.error("Set COMPONENT2_ANNOTATION_MODE=supabase and SUPABASE_IMPORT_DB_URL before importing")
    store = SupabaseAnnotationStore(
        config.supabase_import_db_url,
        run_id=config.annotation_run_id,
        connect_timeout=config.db_connect_timeout,
    )
    report = import_snapshot(store, args.csv, args.seed, source_name=args.source_name)
    print(json.dumps(report.__dict__, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
