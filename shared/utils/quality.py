"""Data validation and quality checks for the shared research datasets.

Checks channels, videos and comments Parquet files with DuckDB SQL (files are
queried in place, not loaded into pandas) and reports problems. It never
changes data: detect -> report -> a later processing stage decides.

Scopes:
  * ``validate_latest()``             data/processed/<dataset>.parquet (one row per id)
  * ``validate_snapshot_quality(id)`` data/snapshots/<id>/<dataset>.parquet (one row per id + collected_at)

Status of a dataset (and of a whole run, the worst of its datasets):
  * VALID                no problems
  * VALID_WITH_WARNINGS  usable, but something should be looked at
  * INVALID              must not be used for research until fixed

Output never contains comment text, commenter identifiers, API keys or secrets.
Examples in issues are limited to public channel / video / comment ids.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal

import duckdb

from shared.schemas.base import INT, STRING, STRING_LIST, TIMESTAMP
from shared.utils.datasets import DATASETS, DatasetSpec, latest_path, snapshot_path
from shared.utils.duckdb_query import MEMORY, duckdb_connection
from shared.utils.paths import snapshot_dir

QUALITY_FILE = "_quality.json"
MAX_EXAMPLES = 5
YOUTUBE_LAUNCH = "2005-04-23 00:00:00+00"  # first public YouTube video
ID_PATTERN = r"[A-Za-z0-9_.\-]{1,128}"  # same rule as shared.schemas.base.YouTubeId
PSEUDONYM = r"anon_[0-9a-f]{64}"  # shared.utils.privacy format

_DUCKDB_TYPES = {STRING: "VARCHAR", INT: "BIGINT", TIMESTAMP: "TIMESTAMP WITH TIME ZONE"}

Severity = Literal["error", "warning"]
Category = Literal["dataset", "schema", "identifier", "duplicate", "relationship", "timestamp", "numeric", "privacy"]


class Status(str, Enum):
    VALID = "VALID"
    VALID_WITH_WARNINGS = "VALID_WITH_WARNINGS"
    INVALID = "INVALID"


@dataclass
class Issue:
    code: str
    severity: Severity
    category: Category
    message: str
    count: int = 0
    examples: list[str] = field(default_factory=list)


@dataclass
class DatasetValidation:
    dataset: str
    source: str
    total_rows: int = 0
    null_counts: dict[str, int] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def status(self) -> Status:
        if self.errors:
            return Status.INVALID
        return Status.VALID_WITH_WARNINGS if self.warnings else Status.VALID

    def _count(self, *categories: str) -> int:
        return sum(i.count for i in self.issues if i.category in categories)

    @property
    def duplicate_count(self) -> int:
        return self._count("duplicate")

    @property
    def relationship_violations(self) -> int:
        return self._count("relationship")

    @property
    def timestamp_violations(self) -> int:
        return self._count("timestamp")

    @property
    def numeric_violations(self) -> int:
        return self._count("numeric")

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "source": self.source,
            "status": self.status.value,
            "total_rows": self.total_rows,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "duplicate_count": self.duplicate_count,
            "relationship_violations": self.relationship_violations,
            "timestamp_violations": self.timestamp_violations,
            "numeric_violations": self.numeric_violations,
            "null_counts": self.null_counts,
            "issues": [asdict(i) for i in self.issues],
        }


@dataclass
class ValidationRun:
    scope: str
    validated_at: str
    results: dict[str, DatasetValidation]

    @property
    def status(self) -> Status:
        statuses = {r.status for r in self.results.values()}
        for s in (Status.INVALID, Status.VALID_WITH_WARNINGS):
            if s in statuses:
                return s
        return Status.VALID

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "validated_at": self.validated_at,
            "status": self.status.value,
            "datasets": {name: r.to_dict() for name, r in self.results.items()},
        }

    def report(self) -> str:
        return format_report(self)


# --- entry points ------------------------------------------------------------------

def validate_latest(datasets: tuple[str, ...] = tuple(DATASETS)) -> ValidationRun:
    """Validate the latest tables (``data/processed/<dataset>.parquet``)."""
    files = {name: latest_path(name) for name in datasets}
    return validate_files(files, scope="latest", unique_by_collection=False)


def validate_snapshot_quality(snapshot_id: str, *, save: bool = True) -> ValidationRun:
    """Validate one snapshot's datasets; optionally save ``_quality.json`` next to it.

    The quality file is derived metadata: it never changes the snapshot's data
    files or its manifest, and can be regenerated at any time.
    """
    from shared.utils.snapshots import get_snapshot  # avoid import cycle

    info = get_snapshot(snapshot_id)
    files = {name: snapshot_path(name, info.snapshot_id) for name in DATASETS
             if snapshot_path(name, info.snapshot_id).is_file() or name in _required(info)}
    run = validate_files(files, scope=f"snapshot:{info.snapshot_id}", unique_by_collection=True,
                         snapshot_date=info.snapshot_id)
    if save:
        _save_quality(info, run)
    return run


def validate_files(
    files: dict[str, Path],
    *,
    scope: str = "custom",
    unique_by_collection: bool = False,
    snapshot_date: str | None = None,
) -> ValidationRun:
    """Validate the given dataset files (keys must be dataset names).

    ``unique_by_collection``: ids may repeat across ``collected_at`` (history,
    snapshots); otherwise each id must appear once (latest tables).
    """
    unknown = [n for n in files if n not in DATASETS]
    if unknown:
        raise ValueError(f"unknown dataset(s) {unknown}; expected {list(DATASETS)}")

    with duckdb_connection(MEMORY) as con:
        results: dict[str, DatasetValidation] = {}
        usable: dict[str, set[str]] = {}  # dataset -> columns with the expected type
        for name, path in files.items():
            result, columns = _validate_structure(con, DATASETS[name], Path(path))
            results[name] = result
            if columns is not None:
                usable[name] = columns
                _check_rows(con, DATASETS[name], result, columns, unique_by_collection, snapshot_date)
        _check_relationships(con, results, usable)

    return ValidationRun(scope=scope, validated_at=_now(), results=results)


# --- structure ---------------------------------------------------------------------

def _validate_structure(con, spec: DatasetSpec, path: Path) -> tuple[DatasetValidation, set[str] | None]:
    result = DatasetValidation(spec.name, _display_path(path))
    if not path.is_file():
        result.issues.append(Issue("dataset_missing", "error", "dataset", f"dataset file not found: {result.source}"))
        return result, None
    sql_path = path.as_posix().replace("'", "''")
    try:
        con.execute(f"CREATE OR REPLACE VIEW {spec.name} AS SELECT * FROM read_parquet('{sql_path}')")
        described = con.execute(f"DESCRIBE {spec.name}").fetchall()
    except duckdb.Error as exc:
        result.issues.append(Issue("dataset_unreadable", "error", "dataset",
                                   f"cannot read Parquet file: {type(exc).__name__}"))
        return result, None

    actual = {row[0]: row[1] for row in described}
    expected = {col: _expected_type(dtype) for col, dtype in spec.model.DTYPES.items()}
    usable = set()
    for col, want in expected.items():
        if col not in actual:
            result.issues.append(Issue("missing_column", "error", "schema", f"missing column '{col}'", 1))
        elif actual[col] != want:
            result.issues.append(Issue("wrong_type", "error", "schema",
                                       f"column '{col}' has type {actual[col]}, expected {want}", 1))
        else:
            usable.add(col)
    extra = sorted(set(actual) - set(expected))
    if extra:
        result.issues.append(Issue("unexpected_columns", "warning", "schema",
                                   f"columns not in the {spec.model.__name__} schema: {extra}", len(extra)))

    result.total_rows = con.execute(f"SELECT count(*) FROM {spec.name}").fetchone()[0]
    nulls = ", ".join(f"count(*) - count({_q(c)})" for c in actual) or "0"
    counts = con.execute(f"SELECT {nulls} FROM {spec.name}").fetchone()
    result.null_counts = {c: int(n) for c, n in zip(actual, counts)}
    if result.total_rows == 0:
        result.issues.append(Issue("empty_dataset", "warning", "dataset", "dataset has no rows"))
    return result, usable


def _expected_type(dtype: Any) -> str:
    if dtype is STRING_LIST or str(dtype).startswith("list<"):
        return "VARCHAR[]"
    return _DUCKDB_TYPES[dtype]


# --- row-level checks -------------------------------------------------------------------

def _check_rows(con, spec: DatasetSpec, result: DatasetValidation, cols: set[str],
                unique_by_collection: bool, snapshot_date: str | None) -> None:
    t, key, add = spec.name, spec.key, result.issues.append
    fields = spec.model.model_fields

    # Required values present.
    for col in [c for c, f in fields.items() if f.is_required() and c in cols]:
        n = result.null_counts.get(col, 0)
        if n:
            add(Issue("null_required", "error", "identifier" if col.endswith("_id") else "dataset",
                      f"{n} row(s) missing required '{col}'", n))

    # Identifier format.
    for col in [c for c in fields if c.endswith("_id") and c in cols and c != "author_channel_id"]:
        n, ex = _count_examples(con, t, key, f"{_q(col)} IS NOT NULL AND NOT regexp_full_match({_q(col)}, ?)",
                                [ID_PATTERN])
        if n:
            add(Issue("invalid_identifier", "error", "identifier", f"{n} invalid '{col}' value(s)", n, ex))
    if "author_channel_id" in cols:
        n, _ = _count_examples(con, t, key, "author_channel_id IS NOT NULL AND NOT regexp_full_match(author_channel_id, ?)",
                               [ID_PATTERN])
        if n:  # examples deliberately omitted: commenter identifiers are never shown
            add(Issue("invalid_identifier", "error", "identifier", f"{n} invalid 'author_channel_id' value(s)", n))
        raw = con.execute(f"SELECT count(*) FROM {t} WHERE author_channel_id IS NOT NULL "
                          "AND NOT regexp_full_match(author_channel_id, ?)", [PSEUDONYM]).fetchone()[0]
        if raw:
            add(Issue("unhashed_commenter_ids", "warning", "privacy",
                      f"{raw} commenter id(s) are not pseudonymized (expected 'anon_' + 64 hex); "
                      "store comments through store_records so ids are hashed", raw))

    # Duplicates.
    if cols >= set(spec.model.DTYPES):
        exact = con.execute(f"SELECT count(*) - count(DISTINCT {t}) FROM {t}").fetchone()[0]
        if exact:
            add(Issue("exact_duplicate_rows", "warning", "duplicate",
                      f"{exact} exact duplicate row(s) (identical in every column)", exact))
    group = [key, "collected_at"] if unique_by_collection else [key]
    if set(group) <= cols:
        g = ", ".join(group)
        rows = con.execute(f"""
            SELECT {key} FROM {t} WHERE {key} IS NOT NULL GROUP BY {g}
            HAVING count(DISTINCT {t}) > 1 ORDER BY {key} LIMIT {MAX_EXAMPLES}""").fetchall()
        n = con.execute(f"""SELECT count(*) FROM (SELECT 1 FROM {t} WHERE {key} IS NOT NULL
                            GROUP BY {g} HAVING count(DISTINCT {t}) > 1)""").fetchone()[0]
        if n:
            per = f"{key} and collected_at" if unique_by_collection else key
            add(Issue("conflicting_duplicates", "error", "duplicate",
                      f"{n} {per} value(s) appear with different data", n, [r[0] for r in rows]))

    # Numbers.
    for col in [c for c, d in spec.model.DTYPES.items() if d == INT and c in cols]:
        n, ex = _count_examples(con, t, key, f"{_q(col)} < 0")
        if n:
            add(Issue("negative_metric", "error", "numeric", f"{n} negative '{col}' value(s)", n, ex))
    if {"like_count", "view_count"} <= cols and t == "videos":
        n, ex = _count_examples(con, t, key, "view_count >= 0 AND like_count > view_count")
        if n:
            add(Issue("likes_exceed_views", "warning", "numeric",
                      f"{n} video(s) with more likes than views (possible stale counts)", n, ex))

    # Timestamps.
    if {"published_at", "collected_at"} <= cols:
        n, ex = _count_examples(con, t, key, "published_at > collected_at")
        if n:
            add(Issue("published_after_collected", "error", "timestamp",
                      f"{n} row(s) published after they were collected", n, ex))
    if "published_at" in cols:
        n, ex = _count_examples(con, t, key, f"published_at < TIMESTAMPTZ '{YOUTUBE_LAUNCH}'")
        if n:
            add(Issue("published_before_youtube", "warning", "timestamp",
                      f"{n} row(s) with published_at before YouTube existed (2005-04-23)", n, ex))
    if "collected_at" in cols:
        n, ex = _count_examples(con, t, key, "collected_at > now() + INTERVAL 1 HOUR")
        if n:
            add(Issue("collected_in_future", "error", "timestamp",
                      f"{n} row(s) with collected_at in the future", n, ex))
        if snapshot_date:
            n, ex = _count_examples(con, t, key, "strftime(collected_at, '%Y-%m-%d') <> ?", [snapshot_date])
            if n:
                add(Issue("outside_snapshot_day", "error", "timestamp",
                          f"{n} row(s) whose collected_at is not on {snapshot_date} (UTC)", n, ex))


# --- relationships ---------------------------------------------------------------------

def _check_relationships(con, results: dict[str, DatasetValidation], usable: dict[str, set[str]]) -> None:
    def ok(name: str, *cols: str) -> bool:
        return name in usable and set(cols) <= usable[name]

    if ok("videos", "channel_id") and ok("channels", "channel_id"):
        n, ex = _count_examples(con, "videos", "video_id",
                                "channel_id NOT IN (SELECT channel_id FROM channels WHERE channel_id IS NOT NULL)")
        if n:
            results["videos"].issues.append(Issue(
                "orphan_videos", "warning", "relationship",
                f"{n} video row(s) reference channels not in the channels dataset", n, ex))

    if ok("comments", "video_id") and ok("videos", "video_id"):
        n, ex = _count_examples(con, "comments", "comment_id",
                                "video_id NOT IN (SELECT video_id FROM videos WHERE video_id IS NOT NULL)")
        if n:
            results["comments"].issues.append(Issue(
                "orphan_comments", "warning", "relationship",
                f"{n} comment row(s) reference videos not in the videos dataset", n, ex))

    if ok("comments", "video_id", "channel_id") and ok("videos", "video_id", "channel_id"):
        n, ex = _count_examples(con, "comments", "comment_id", """
            EXISTS (SELECT 1 FROM videos v WHERE v.video_id = comments.video_id
                    AND v.channel_id <> comments.channel_id)""")
        if n:
            results["comments"].issues.append(Issue(
                "comment_channel_mismatch", "error", "relationship",
                f"{n} comment(s) whose channel_id differs from their video's channel", n, ex))

    if ok("comments", "video_id", "published_at") and ok("videos", "video_id", "published_at"):
        n, ex = _count_examples(con, "comments", "comment_id", """
            EXISTS (SELECT 1 FROM videos v WHERE v.video_id = comments.video_id
                    AND comments.published_at < v.published_at)""")
        if n:
            results["comments"].issues.append(Issue(
                "comment_before_video", "warning", "timestamp",
                f"{n} comment(s) published before their video", n, ex))


# --- snapshots ---------------------------------------------------------------------

def quality_path(snapshot_id: str) -> Path:
    return snapshot_dir(snapshot_id) / QUALITY_FILE


def load_snapshot_quality(snapshot_id: str) -> dict[str, Any] | None:
    path = quality_path(snapshot_id)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def is_research_ready(snapshot_id: str) -> bool:
    """Complete, unchanged since sealing, and its saved validation is not INVALID
    and was made for exactly the sealed files."""
    from shared.utils.snapshots import _load_manifest, get_snapshot, verify_snapshot

    info = get_snapshot(snapshot_id)
    if info.status != "complete" or not verify_snapshot(info.snapshot_id).ok:
        return False
    quality = load_snapshot_quality(info.snapshot_id)
    if quality is None or quality.get("status") == Status.INVALID.value:
        return False
    sealed = {n: m["sha256"] for n, m in _load_manifest(info.snapshot_id)["datasets"].items()}
    return quality.get("validated_files") == sealed


def latest_research_ready_snapshot() -> str | None:
    from shared.utils.snapshots import list_snapshots

    ready = [i.snapshot_id for i in list_snapshots(status="complete") if is_research_ready(i.snapshot_id)]
    return ready[-1] if ready else None


def _required(info) -> tuple[str, ...]:
    try:
        from shared.utils.snapshots import _load_manifest
        return tuple(_load_manifest(info.snapshot_id).get("required_datasets", DATASETS))
    except Exception:
        return tuple(DATASETS)


def _save_quality(info, run: ValidationRun) -> None:
    from shared.utils.snapshots import _sha256

    data = run.to_dict()
    data["snapshot_status"] = info.status
    data["validated_files"] = {
        name: _sha256(snapshot_path(name, info.snapshot_id))
        for name in run.results if snapshot_path(name, info.snapshot_id).is_file()
    }
    path = quality_path(info.snapshot_id)
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


# --- report ------------------------------------------------------------------------

def format_report(run: ValidationRun) -> str:
    lines = [f"Data validation report - {run.scope} ({run.validated_at})",
             f"Overall: {run.status.value}", ""]
    for name, r in run.results.items():
        lines.append(f"{name.upper():<9} {r.status.value:<20} rows={r.total_rows:<8} "
                     f"errors={len(r.errors)} warnings={len(r.warnings)} duplicates={r.duplicate_count} "
                     f"relationship={r.relationship_violations} timestamp={r.timestamp_violations} "
                     f"numeric={r.numeric_violations}")
        for issue in r.errors + r.warnings:
            tag = "ERROR" if issue.severity == "error" else "WARN "
            ex = f" (e.g. {', '.join(issue.examples)})" if issue.examples else ""
            lines.append(f"  {tag} [{issue.category}] {issue.message}{ex}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# --- helpers ---------------------------------------------------------------------

def _count_examples(con, table: str, key: str, condition: str, params: list[Any] | None = None) -> tuple[int, list[str]]:
    """Count rows matching ``condition`` and return up to MAX_EXAMPLES of their ids.

    ``table``, ``key`` and ``condition`` are built from fixed schema names only;
    values are passed as parameters.
    """
    params = params or []
    n = con.execute(f"SELECT count(*) FROM {table} WHERE {condition}", params).fetchone()[0]
    if not n:
        return 0, []
    rows = con.execute(
        f"SELECT DISTINCT {key} FROM {table} WHERE {condition} AND {key} IS NOT NULL ORDER BY 1 LIMIT {MAX_EXAMPLES}",
        params,
    ).fetchall()
    return int(n), [str(r[0]) for r in rows]


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _display_path(path: Path) -> str:
    from shared.utils import paths
    try:
        return path.relative_to(paths.PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    """python -m shared.utils.quality latest | snapshot <YYYY-MM-DD>"""
    import argparse

    parser = argparse.ArgumentParser(prog="quality", description="Validate the shared research datasets.")
    sub = parser.add_subparsers(dest="scope", required=True)
    sub.add_parser("latest", help="validate data/processed/*.parquet")
    p = sub.add_parser("snapshot", help="validate one snapshot and save _quality.json")
    p.add_argument("snapshot_id")
    args = parser.parse_args(argv)
    run = validate_latest() if args.scope == "latest" else validate_snapshot_quality(args.snapshot_id)
    print(run.report())
    return 1 if run.status is Status.INVALID else 0


if __name__ == "__main__":
    sys.exit(main())
