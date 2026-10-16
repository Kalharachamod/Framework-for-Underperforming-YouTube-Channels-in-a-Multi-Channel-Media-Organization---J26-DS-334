"""Evaluate the frozen rule baseline against the approved 40-row calibration set."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .baseline import SIGNAL_CLASSES, detect_comment


EXPERIMENT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = EXPERIMENT_DIR / "outputs" / "calibration_40_comments.csv"
DEFAULT_OUTPUT_DIR = EXPERIMENT_DIR / "outputs" / "calibration_40_evaluation"
REQUIRED_COLUMNS = {
    "comment_id",
    "channel_name",
    "video_title",
    "video_description",
    "original_text",
    "human_primary_signal",
    "human_actionable_content_demand",
    "human_requested_action",
    "human_requested_topic",
    "human_notes",
}
VALID_ACTIONABILITY = {"YES", "NO", "UNCLEAR"}


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def validate_calibration(rows: list[dict[str, str]]) -> dict[str, Any]:
    if len(rows) != 40:
        raise ValueError(f"Expected exactly 40 calibration rows, found {len(rows)}")
    if not rows:
        raise ValueError("Calibration CSV is empty")
    missing = sorted(REQUIRED_COLUMNS.difference(rows[0]))
    if missing:
        raise ValueError(f"Calibration CSV is missing columns: {missing}")
    comment_ids = [row["comment_id"].strip() for row in rows]
    if any(not comment_id for comment_id in comment_ids):
        raise ValueError("Every calibration row must have a comment_id")
    if len(set(comment_ids)) != len(comment_ids):
        raise ValueError("Calibration comment IDs must be unique")

    invalid_primary = sorted({row["human_primary_signal"].strip() for row in rows} - set(SIGNAL_CLASSES))
    invalid_actionability = sorted({row["human_actionable_content_demand"].strip() for row in rows} - VALID_ACTIONABILITY)
    incomplete = [
        index + 1
        for index, row in enumerate(rows)
        if not row["human_primary_signal"].strip() or not row["human_actionable_content_demand"].strip()
    ]
    if invalid_primary or invalid_actionability or incomplete:
        raise ValueError(
            "Invalid or incomplete human annotations: "
            f"primary={invalid_primary}, actionability={invalid_actionability}, incomplete_rows={incomplete}"
        )
    return {
        "rows": len(rows),
        "unique_comment_ids": len(set(comment_ids)),
        "human_primary_signal_counts": dict(Counter(row["human_primary_signal"].strip() for row in rows)),
        "human_actionable_content_demand_counts": dict(
            Counter(row["human_actionable_content_demand"].strip() for row in rows)
        ),
    }


def _metric(numerator: int, denominator: int) -> float | str:
    return round(numerator / denominator, 6) if denominator else "N/A"


def binary_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    evaluated = [record for record in records if record["human_actionable_content_demand"] != "UNCLEAR"]
    tp = sum(record["baseline_candidate_for_content_demand"] and record["human_actionable_content_demand"] == "YES" for record in evaluated)
    fp = sum(record["baseline_candidate_for_content_demand"] and record["human_actionable_content_demand"] == "NO" for record in evaluated)
    fn = sum((not record["baseline_candidate_for_content_demand"]) and record["human_actionable_content_demand"] == "YES" for record in evaluated)
    tn = sum((not record["baseline_candidate_for_content_demand"]) and record["human_actionable_content_demand"] == "NO" for record in evaluated)
    return {
        "rows_total": len(records),
        "rows_excluded_human_unclear": len(records) - len(evaluated),
        "rows_evaluated": len(evaluated),
        "TP": int(tp),
        "FP": int(fp),
        "FN": int(fn),
        "TN": int(tn),
        "precision": _metric(tp, tp + fp),
        "recall": _metric(tp, tp + fn),
        "F1": _metric(2 * tp, 2 * tp + fp + fn),
        "specificity": _metric(tn, tn + fp),
        "accuracy": _metric(tp + tn, len(evaluated)),
    }


def _disagreement_type(human_actionability: str, baseline_candidate: bool) -> str:
    if human_actionability == "UNCLEAR":
        return "HUMAN_ACTIONABILITY_UNCLEAR_EXCLUDED"
    if human_actionability == "YES" and baseline_candidate:
        return "TRUE_POSITIVE"
    if human_actionability == "NO" and baseline_candidate:
        return "FALSE_POSITIVE"
    if human_actionability == "YES" and not baseline_candidate:
        return "FALSE_NEGATIVE"
    return "TRUE_NEGATIVE"


def _error_reason(record: dict[str, Any]) -> str:
    disagreement = record["binary_disagreement_type"]
    human_signal = record["human_primary_signal"]
    baseline_signal = record["baseline_primary_signal"]
    evidence = record["baseline_evidence_span"] or "no direct evidence span"
    if disagreement == "FALSE_POSITIVE":
        if human_signal == "ORDINARY_REACTION":
            return f"The broad rule fired on {evidence!r}, but the reviewer treated the comment as praise, support, or a reaction rather than a future-content request."
        if human_signal == "TOPICAL_INTEREST_OR_DISCUSSION":
            return f"The rule detected {evidence!r} or contextual overlap and treated it as a candidate, while the reviewer judged it to be discussion of the current topic rather than a channel request."
        if human_signal == "CONTENT_QUALITY_FEEDBACK":
            return f"The baseline signal {baseline_signal} treated {evidence!r} as actionable, but the reviewer recorded non-actionable general quality commentary."
        if human_signal == "UNCLEAR":
            return f"The baseline fired on {evidence!r}, but the reviewer found insufficient evidence for actionable demand."
        return f"The baseline candidate rule fired on {evidence!r}, while the human actionability label was NO."
    if disagreement == "FALSE_NEGATIVE":
        if human_signal == "CONTENT_CHANGE_PREFERENCE":
            return "The reviewer identified an implicit or contextual presentation/cast/story preference that the lexical candidate rules did not mark as actionable."
        if human_signal == "EXPLICIT_CONTENT_REQUEST":
            return "The reviewer identified a direct request whose wording was not covered by the current request patterns."
        if human_signal == "INFORMATION_NEED":
            return "The reviewer identified an information or availability need that did not satisfy the baseline's context-sensitive request conditions."
        return "The reviewer marked the row YES, but the current rule evidence was insufficient to trigger the candidate flag."
    return "No binary error reason applies."


def evaluate(rows: list[dict[str, str]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows, start=1):
        prediction = detect_comment(row)
        baseline_candidate = bool(prediction["candidate_for_content_demand"])
        record: dict[str, Any] = {
            "row_number": row_number,
            "calibration_order": row.get("calibration_order", ""),
            "comment_id": row["comment_id"],
            "channel_name": row["channel_name"],
            "video_title": row["video_title"],
            "video_description": row["video_description"],
            "original_text": row["original_text"],
            "human_primary_signal": row["human_primary_signal"],
            "human_actionable_content_demand": row["human_actionable_content_demand"],
            "human_requested_action": row["human_requested_action"],
            "human_requested_topic": row["human_requested_topic"],
            "human_notes": row["human_notes"],
            "baseline_primary_signal": prediction["primary_signal"],
            "baseline_candidate_for_content_demand": baseline_candidate,
            "baseline_actionable_content_demand": "YES" if baseline_candidate else "NO",
            "baseline_secondary_signals": prediction["secondary_signals"],
            "baseline_evidence_span": prediction["evidence_span"] or "",
            "baseline_requested_action": prediction["requested_action"] or "",
            "baseline_requested_topic": prediction["requested_topic"] or "",
            "baseline_requested_format": prediction["requested_format"] or "",
            "baseline_uncertainty_reason": prediction["uncertainty_reason"] or "",
            "baseline_score": prediction["baseline_score"],
        }
        record["binary_disagreement_type"] = _disagreement_type(
            record["human_actionable_content_demand"], baseline_candidate
        )
        record["primary_signal_agreement"] = record["human_primary_signal"] == record["baseline_primary_signal"]
        record["error_reason"] = _error_reason(record)
        records.append(record)

    human_classes = list(SIGNAL_CLASSES)
    matrix = {human: {baseline: 0 for baseline in human_classes} for human in human_classes}
    for record in records:
        matrix[record["human_primary_signal"]][record["baseline_primary_signal"]] += 1
    exact = sum(record["primary_signal_agreement"] for record in records)
    return records, {
        "exact_primary_signal_agreement_count": exact,
        "exact_primary_signal_agreement_rate": _metric(exact, len(records)),
        "signal_confusion_matrix": matrix,
    }


def _channel_summaries(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for channel in sorted({record["channel_name"] for record in records}):
        channel_records = [record for record in records if record["channel_name"] == channel]
        metrics = binary_metrics(channel_records)
        summaries.append({"channel_name": channel, **metrics})
    return summaries


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    body = [
        "| " + " | ".join(str(row.get(column, "N/A")) for column in columns) + " |"
        for row in rows
    ]
    return "\n".join([header, separator, *body])


def _render_report(
    input_path: Path,
    validation: dict[str, Any],
    records: list[dict[str, Any]],
    overall: dict[str, Any],
    channel_summaries: list[dict[str, Any]],
) -> str:
    metrics = binary_metrics(records)
    matrix = overall["signal_confusion_matrix"]
    matrix_rows = []
    for human in SIGNAL_CLASSES:
        matrix_rows.append({"human\\baseline": human, **matrix[human]})

    errors = [record for record in records if record["binary_disagreement_type"] in {"FALSE_POSITIVE", "FALSE_NEGATIVE"}]
    false_positives = [record for record in records if record["binary_disagreement_type"] == "FALSE_POSITIVE"]
    false_negatives = [record for record in records if record["binary_disagreement_type"] == "FALSE_NEGATIVE"]
    false_positive_signals = Counter(record["human_primary_signal"] for record in false_positives)
    trigger_counts = Counter(
        record["baseline_evidence_span"].casefold()
        for record in false_positives
        if record["baseline_evidence_span"]
    )
    trigger_summary = ", ".join(f"`{trigger}` ({count})" for trigger, count in trigger_counts.most_common()) or "none"
    error_rows = [
        {
            "row": record["row_number"],
            "type": record["binary_disagreement_type"],
            "channel": record["channel_name"],
            "human": record["human_primary_signal"],
            "baseline": record["baseline_primary_signal"],
            "evidence": record["baseline_evidence_span"] or "N/A",
            "reason": record["error_reason"],
        }
        for record in errors
    ]
    error_section = _markdown_table(
        error_rows,
        ["row", "type", "channel", "human", "baseline", "evidence", "reason"],
    ) if error_rows else "No binary false positives or false negatives were observed."

    return f"""# Experiment 1: Rule Baseline vs Human Calibration

## Scope and methodology

- Input: `{input_path}`
- Calibration rows: `{validation['rows']}` with `{validation['unique_comment_ids']}` unique comment IDs.
- The 40 rows were deliberately selected as 20 prior baseline candidates and 20 controls across five channels. They are not representative of viewers or channel traffic.
- The existing `baseline.detect_comment()` implementation was executed as-is. No thresholds, patterns, taxonomy, or rules were tuned before recording these results.
- Human labels were reviewed and approved by the researcher. AI-assisted suggestions were available during the review process, but the final annotation decisions are attributed to the researcher, not Codex.
- For binary metrics, human `YES` is positive and `NO` is negative. Human `UNCLEAR` rows are excluded and reported separately.
- The baseline candidate flag is intentionally broader than strict actionable demand, so precision is expected to be affected by this definition mismatch.

## Validation and human labels

- Human primary-signal labels: `{validation['human_primary_signal_counts']}`
- Human actionability labels: `{validation['human_actionable_content_demand_counts']}`
- Binary rows evaluated: `{metrics['rows_evaluated']}`
- Rows excluded because human actionability was `UNCLEAR`: `{metrics['rows_excluded_human_unclear']}`

## Binary diagnostics

{_markdown_table([metrics], ['TP', 'FP', 'FN', 'TN', 'precision', 'recall', 'F1', 'specificity', 'accuracy'])}

Metrics are diagnostics for this deliberately selected calibration set only. They are not final model accuracy results and do not estimate demand prevalence.

## Primary-signal confusion matrix

Rows are human primary signals; columns are baseline primary signals.

{_markdown_table(matrix_rows, ['human\\baseline', *SIGNAL_CLASSES])}

- Exact primary-signal agreement: `{overall['exact_primary_signal_agreement_count']}/{len(records)}` (`{overall['exact_primary_signal_agreement_rate']}`)

## Channel summaries

{_markdown_table(channel_summaries, ['channel_name', 'rows_total', 'rows_evaluated', 'rows_excluded_human_unclear', 'TP', 'FP', 'FN', 'TN', 'precision', 'recall', 'F1', 'specificity', 'accuracy'])}

## Error inspection

The following disagreements were inspected using the original comment, video
context, human note, and baseline evidence span. The rule baseline is a
candidate screener, not a strict demand adjudicator; false positives often
reflect that deliberately broad design.

Observed patterns:

- False positives: `{len(false_positives)}`. Human signals among them were `{dict(false_positive_signals)}`.
- The observed baseline evidence spans were `{trigger_summary}`. These include ordinary words and romanized Sinhala forms that appear in praise, names, song/episode references, current-topic opinions, or unclear fragments rather than requests to the channel.
- False negatives: `{len(false_negatives)}`. The observed case was an implicit storyline preference addressed to the drama writer, which the current lexical request rules did not recognize.

{error_section}

## Limitations

The calibration sample is balanced toward baseline candidates and controls,
not sampled to estimate population prevalence. Human `UNCLEAR` rows are not
treated as negative examples. The eight-class agreement result is sensitive to
the experimental taxonomy and should not be interpreted as a production label
accuracy result. The evaluation used no Supabase data, no additional API calls,
and no newly trained model.

## Recommended next experiments

1. Double-annotate a larger representative sample and adjudicate disagreements
   before estimating prevalence or recall.
2. Expand the error audit by language/script and channel, especially implicit
   storyline or format preferences and current-topic discussions.
3. Refine the taxonomy only through an approved annotation-guideline change;
   do not tune rules against this calibration set alone.
4. Keep a representative evaluation sample separate from any demand-enriched
   training or topic-discovery sample.
"""


def run(input_path: Path, output_dir: Path) -> dict[str, Any]:
    rows = _read_rows(input_path)
    validation = validate_calibration(rows)
    records, primary_summary = evaluate(rows)
    metrics = binary_metrics(records)
    channels = _channel_summaries(records)
    output_dir.mkdir(parents=True, exist_ok=True)

    audit_fields = [
        "row_number", "calibration_order", "comment_id", "channel_name", "video_title", "video_description",
        "original_text", "human_primary_signal", "human_actionable_content_demand", "human_requested_action",
        "human_requested_topic", "human_notes", "baseline_primary_signal", "baseline_candidate_for_content_demand",
        "baseline_actionable_content_demand", "baseline_secondary_signals", "baseline_evidence_span",
        "baseline_requested_action", "baseline_requested_topic", "baseline_requested_format",
        "baseline_uncertainty_reason", "baseline_score", "binary_disagreement_type", "primary_signal_agreement",
        "error_reason",
    ]
    _write_csv(output_dir / "per_comment_audit.csv", records, audit_fields)
    _write_csv(output_dir / "channel_summary.csv", channels, list(channels[0]) if channels else ["channel_name"])
    matrix_rows = [{"human_primary_signal": human, **primary_summary["signal_confusion_matrix"][human]} for human in SIGNAL_CLASSES]
    _write_csv(output_dir / "signal_confusion_matrix.csv", matrix_rows, ["human_primary_signal", *SIGNAL_CLASSES])
    _write_csv(output_dir / "binary_metrics.csv", [metrics], list(metrics))
    summary = {
        "input": str(input_path),
        "validation": validation,
        "binary_metrics": metrics,
        "primary_signal_summary": primary_summary,
        "channel_summary": channels,
    }
    (output_dir / "metrics.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "first_calibration_report.md").write_text(
        _render_report(input_path, validation, records, primary_summary, channels),
        encoding="utf-8",
    )
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    summary = run(args.input, args.output_dir)
    print(f"Validated rows: {summary['validation']['rows']}; unique IDs: {summary['validation']['unique_comment_ids']}")
    print(f"Evaluated binary rows: {summary['binary_metrics']['rows_evaluated']}; excluded UNCLEAR: {summary['binary_metrics']['rows_excluded_human_unclear']}")
    print(f"TP={summary['binary_metrics']['TP']} FP={summary['binary_metrics']['FP']} FN={summary['binary_metrics']['FN']} TN={summary['binary_metrics']['TN']}")
    print(f"Report: {args.output_dir / 'first_calibration_report.md'}")


if __name__ == "__main__":
    main()
