"""Experiment 3C provenance and blind re-check for annotation batch 1.

Batch 1 labels were produced with AI pre-labelling and reviewed by the
researcher in a copy of the AI suggestion sheet. They are recorded with the
provenance ``ai_suggested_researcher_reviewed``, never as independent human
annotation. A blind re-check of a stratified subset (no AI columns, new IDs,
shuffled) measures how far the reviewed labels agree with the researcher's own
unassisted judgement; Cohen's kappa on that subset is the reliability evidence
reported for batch 1.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .annotation_schema import ACTIONABILITY_LABELS, PRIMARY_SIGNALS, SPAM_STATUS_LABELS
from .audit import sha256
from .build_expanded_corpus import DEFAULT_OUTPUT_DIR as CORPUS_DIR
from .build_expanded_corpus import ExpandedCorpusGuard
from .prepare_experiment_3c import ANNOTATION_COLUMNS, CONTEXT_COLUMNS, DEFAULT_OUTPUT_DIR, write_workbook


PROVENANCE = "ai_suggested_researcher_reviewed"
RECHECK_SEED = 20261022
RECHECK_STRATA = {"YES": 20, "UNCLEAR": 5, "NO": 35}
REVIEWED_SHEET = "Annotation_by me"
LABEL_COLUMNS = {
    "primary signal": "primary_signal",
    "actionable_content_demand": "actionable_content_demand",
    "requested_action": "requested_action",
    "requested_topic": "requested_topic",
    "request_target": "request_target",
    "spam_status": "spam_status",
}
DEFAULT_REVIEWED = DEFAULT_OUTPUT_DIR / "returned" / "annotation_batch1_ai_assisted_reviewed.xlsx"


def _rank(value: str, namespace: str, seed: int = RECHECK_SEED) -> str:
    return hashlib.sha256(f"{seed}:{namespace}:{value}".encode("utf-8")).hexdigest()


def import_reviewed_labels(
    workbook: Path,
    batch_dir: Path = DEFAULT_OUTPUT_DIR,
    sheet: str = REVIEWED_SHEET,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    sheets = pd.read_excel(workbook, sheet_name=None, dtype=str)
    if sheet not in sheets:
        raise ValueError(f"Sheet {sheet!r} not found; available: {sorted(sheets)}")
    reviewed = sheets[sheet].fillna("")
    batch = pd.read_csv(batch_dir / "annotation_batch1.csv", dtype=str, keep_default_na=False, encoding="utf-8-sig")
    key = pd.read_csv(batch_dir / "annotation_batch1_private_key.csv", dtype=str, keep_default_na=False)

    if reviewed["review_id"].tolist() != batch["review_id"].tolist():
        raise ValueError("Reviewed sheet rows do not match annotation batch 1 review IDs")
    # Spreadsheet round trips turn CRLF into LF and may trim outer spaces; any
    # other difference means the comment itself was edited.
    def _comparable(series: pd.Series) -> pd.Series:
        return series.str.replace("\r\n", "\n", regex=False).str.strip()

    if not _comparable(reviewed["comment_text"]).eq(_comparable(batch["comment_text"])).all():
        raise ValueError("Comment text was changed in the reviewed sheet")
    missing = sorted(set(LABEL_COLUMNS).difference(reviewed.columns))
    if missing:
        raise ValueError(f"Reviewed sheet is missing label columns: {missing}")

    labels = reviewed[["review_id", *LABEL_COLUMNS]].rename(columns=LABEL_COLUMNS)
    for column in labels.columns:
        labels[column] = labels[column].str.strip()
    for column, allowed in (
        ("primary_signal", PRIMARY_SIGNALS),
        ("actionable_content_demand", ACTIONABILITY_LABELS),
        ("spam_status", SPAM_STATUS_LABELS),
    ):
        invalid = sorted(set(labels[column]).difference(allowed))
        if invalid:
            raise ValueError(f"{column} has invalid values: {invalid}")
    labels = key.merge(labels, on="review_id", validate="one_to_one")
    labels["label_provenance"] = PROVENANCE

    review_columns = [c for c in reviewed.columns if c.startswith("human_")]
    provenance = {
        "label_provenance": PROVENANCE,
        "source_file_sha256": sha256(workbook),
        "source_sheet": sheet,
        "rows": int(len(labels)),
        "actionability_counts": labels["actionable_content_demand"].value_counts().to_dict(),
        "primary_signal_counts": labels["primary_signal"].value_counts().to_dict(),
        "per_row_review_columns_filled": {c: int(reviewed[c].str.strip().ne("").sum()) for c in review_columns},
        "note": (
            "Labels originate from AI pre-labelling reviewed by the researcher. Per-row corrections were not "
            "recorded, so these labels are not independent human annotation. Reliability is reported from the "
            "blind re-check subset. Held-out evaluation labels must be produced blind without AI suggestions."
        ),
    }
    return labels, provenance


def build_recheck(labels: pd.DataFrame, batch_dir: Path = DEFAULT_OUTPUT_DIR) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Stratified, shuffled subset with new IDs and no label or AI columns."""

    ranked = labels.assign(rank=labels["review_id"].map(lambda v: _rank(v, "select")))
    parts = [
        ranked[ranked["actionable_content_demand"].eq(label)].sort_values("rank").head(n)
        for label, n in RECHECK_STRATA.items()
    ]
    picked = pd.concat(parts)
    picked = picked.assign(order=picked["review_id"].map(lambda v: _rank(v, "order"))).sort_values("order")
    picked["recheck_id"] = [f"RC-{i + 1:03d}" for i in range(len(picked))]

    batch = pd.read_csv(batch_dir / "annotation_batch1.csv", dtype=str, keep_default_na=False, encoding="utf-8-sig")
    rows = picked[["recheck_id", "review_id"]].merge(batch, on="review_id", validate="one_to_one")
    key = rows[["recheck_id", "review_id"]].copy()
    rows["review_id"] = rows["recheck_id"]
    for column in ANNOTATION_COLUMNS:
        rows[column] = ""
    return rows[CONTEXT_COLUMNS + ANNOTATION_COLUMNS], key


RECHECK_GUIDE = [
    "Component 2 blind re-check (60 comments)",
    "",
    "These comments are a shuffled subset with new IDs. Label them from scratch, on your own judgement only.",
    "Do not open the earlier batch-1 files or any AI suggestions while doing this sheet.",
    "Ideally do this at least a day after reviewing batch 1.",
    "",
    "Fill the yellow columns exactly as in batch 1 (same eight primary signals, YES/NO/UNCLEAR actionability,",
    "spam status, and requested action/topic/target when YES). The batch-1 Guide definitions still apply:",
    "   YES only if the channel itself could act on it; implicit requests count; praise containing 'please' is NO.",
    "",
    "The agreement between this sheet and the batch-1 labels is reported as the reliability of batch 1.",
]


def agreement(recheck_workbook: Path, labels: pd.DataFrame, key: pd.DataFrame) -> dict[str, Any]:
    from sklearn.metrics import cohen_kappa_score

    blind = pd.read_excel(recheck_workbook, sheet_name="Annotate", dtype=str).fillna("")
    blind = blind.rename(columns={"review_id": "recheck_id"}).merge(key, on="recheck_id", validate="one_to_one")
    merged = blind.merge(labels, on="review_id", validate="one_to_one")
    done = merged["annotator_1_actionable_content_demand"].str.strip().ne("")
    merged = merged[done]
    result: dict[str, Any] = {"compared_rows": int(len(merged))}
    for blind_column, label_column in (
        ("annotator_1_actionable_content_demand", "actionable_content_demand"),
        ("annotator_1_primary_signal", "primary_signal"),
    ):
        a = merged[blind_column].str.strip()
        b = merged[label_column]
        result[label_column] = {
            "raw_agreement": float((a == b).mean()) if len(merged) else None,
            "cohen_kappa": float(cohen_kappa_score(a, b)) if len(merged) > 1 else None,
            "confusion": pd.crosstab(a.rename("blind"), b.rename("batch1")).to_dict(),
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Record batch-1 provenance and build or score the blind re-check.")
    parser.add_argument("--reviewed", type=Path, default=DEFAULT_REVIEWED)
    parser.add_argument("--score", type=Path, help="Completed blind re-check workbook to score.")
    args = parser.parse_args()
    out = DEFAULT_OUTPUT_DIR
    labels, provenance = import_reviewed_labels(args.reviewed)
    ExpandedCorpusGuard.load(CORPUS_DIR / "comment_partition_manifest_v2.csv").validate_training_frame(labels[["comment_id"]])
    labels.to_csv(out / "annotation_batch1_504.csv", index=False, encoding="utf-8")
    (out / "annotation_batch1_provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    if args.score:
        key = pd.read_csv(out / "recheck_private_key.csv", dtype=str)
        result = agreement(args.score, labels, key)
        (out / "recheck_agreement.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0
    rows, key = build_recheck(labels)
    write_workbook(rows, out / "blind_recheck_60.xlsx", guide_lines=RECHECK_GUIDE)
    key.to_csv(out / "recheck_private_key.csv", index=False, encoding="utf-8")
    print(json.dumps({"recheck_rows": len(rows), "provenance": provenance}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
