"""Research snapshot management.

A snapshot is one UTC collection day: ``data/snapshots/<YYYY-MM-DD>/`` holding
``channels.parquet``, ``videos.parquet`` and ``comments.parquet`` with every
observation collected that day (written by ``store_records``).

Life cycle:

* **incomplete**: the folder is still being filled by collection runs.
* **complete**: ``create_snapshot`` validated the files and wrote the manifest
  ``_snapshot.json`` (row counts, schema version, SHA-256 per file). From then
  on the snapshot is immutable: ``store_records`` refuses to change it.
* **invalid**: the manifest is unreadable or its files are missing.

The manifest is written last and atomically, so a failure part-way never leaves
a snapshot that looks complete.

Research snapshots (same manifest format, checksums and immutability) freeze the
FULL current dataset at one extraction point, e.g. from Supabase:
``data/snapshots/research/rs-<YYYYMMDDTHHMMSSZ>/``. They are written once, never
modified, and are not part of the day-snapshot history views.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

import duckdb
import pandas as pd

from shared.schemas import SCHEMA_VERSION
from shared.utils.datasets import (
    COLLECTED_AT,
    DATASETS,
    MANIFEST_NAME,
    _conform,
    get_spec,
    snapshot_path,
)
from shared.utils.duckdb_query import MEMORY, duckdb_connection
from shared.utils import privacy
from shared.utils.parquet_io import DatasetNotFoundError, DatasetReadError, SchemaError, read_dataset, write_dataset
from shared.utils.paths import get_data_paths, snapshot_dir

MANIFEST_VERSION = 1
DEFAULT_SOURCE = "youtube_data_api"
ALL_DATASETS: tuple[str, ...] = tuple(DATASETS)

Status = Literal["complete", "incomplete", "invalid"]

_SNAPSHOT_ID = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SOURCE = re.compile(r"^[a-z0-9_]{1,64}$")


class SnapshotNotFoundError(FileNotFoundError):
    """No snapshot with that id exists (or none is complete)."""


class SnapshotExistsError(FileExistsError):
    """The snapshot is already complete; replacing it needs ``replace=True``."""


class SnapshotValidationError(ValueError):
    """The snapshot failed validation; ``errors`` lists every problem found."""

    def __init__(self, snapshot_id: str, errors: list[str]):
        self.snapshot_id = snapshot_id
        self.errors = errors
        super().__init__(f"Snapshot {snapshot_id} is not valid:\n- " + "\n- ".join(errors))


@dataclass(frozen=True)
class SnapshotInfo:
    snapshot_id: str
    path: Path
    status: Status
    datasets: tuple[str, ...]          # dataset files present in the folder
    created_at: datetime | None = None  # when the snapshot was sealed
    row_counts: dict[str, int] = field(default_factory=dict)
    problem: str | None = None


@dataclass
class ValidationReport:
    snapshot_id: str
    errors: list[str] = field(default_factory=list)
    datasets: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


# --- ids and paths ---------------------------------------------------------------

def normalize_snapshot_id(snapshot_id: date | str) -> str:
    """Snapshot ids are UTC dates: ``YYYY-MM-DD``."""
    if isinstance(snapshot_id, datetime):
        raise ValueError("snapshot id must be a date, not a datetime")
    if isinstance(snapshot_id, date):
        return snapshot_id.isoformat()
    if isinstance(snapshot_id, str) and _SNAPSHOT_ID.match(snapshot_id.strip()):
        try:
            return date.fromisoformat(snapshot_id.strip()).isoformat()
        except ValueError:
            pass
    raise ValueError(f"invalid snapshot id {snapshot_id!r}; expected a date like '2026-10-07'")


def manifest_path(snapshot_id: date | str) -> Path:
    return snapshot_dir(normalize_snapshot_id(snapshot_id)) / MANIFEST_NAME


# --- create / validate -------------------------------------------------------------

def validate_snapshot(
    snapshot_id: date | str, *, required: Sequence[str] = ALL_DATASETS
) -> ValidationReport:
    """Check that a snapshot's files are complete, readable and schema-valid.

    Never raises for data problems; they are collected in ``report.errors``.
    """
    sid = normalize_snapshot_id(snapshot_id)
    report = ValidationReport(sid)
    folder = snapshot_dir(sid)
    if not folder.is_dir():
        report.errors.append(f"snapshot folder does not exist: {folder}")
        return report

    # Required datasets must exist; other datasets present are validated too.
    present = [n for n in DATASETS if snapshot_path(n, sid).is_file()]
    for name in [n for n in DATASETS if n in required or n in present]:
        spec = get_spec(name)
        path = snapshot_path(name, sid)
        if not path.is_file():
            report.errors.append(f"{name}: missing {path.name}")
            continue
        try:
            df = _conform(spec, read_dataset(path), path)
        except (DatasetReadError, SchemaError) as exc:
            report.errors.append(f"{name}: {exc}")
            continue
        problems = _check_rows(spec, df, sid)
        report.errors.extend(f"{name}: {p}" for p in problems)
        if not problems:
            report.datasets[name] = _dataset_metadata(spec, df, path)
    return report


def create_snapshot(
    snapshot_id: date | str,
    *,
    required: Sequence[str] = ALL_DATASETS,
    source: str = DEFAULT_SOURCE,
    replace: bool = False,
) -> SnapshotInfo:
    """Validate a collection day and seal it as a complete, immutable snapshot.

    Raises ``SnapshotExistsError`` if it is already complete (unless
    ``replace=True``) and ``SnapshotValidationError`` if any check fails; in
    both cases nothing is written.
    """
    sid = normalize_snapshot_id(snapshot_id)
    if not _SOURCE.match(source or ""):
        raise ValueError(f"source must be a short lowercase identifier, got {source!r}")
    unknown = [d for d in required if d not in DATASETS]
    if unknown or not required:
        raise ValueError(f"required must be a non-empty subset of {list(DATASETS)}, got {list(required)}")

    target = manifest_path(sid)
    if target.exists() and not replace:
        raise SnapshotExistsError(
            f"Snapshot {sid} is already complete; pass replace=True to re-seal it deliberately"
        )
    if not snapshot_dir(sid).is_dir():
        raise SnapshotNotFoundError(f"No data stored for snapshot {sid}: {snapshot_dir(sid)}")

    report = validate_snapshot(sid, required=required)
    if not report.ok:
        raise SnapshotValidationError(sid, report.errors)

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "snapshot_id": sid,
        "created_at": _utcnow().isoformat().replace("+00:00", "Z"),
        "source": source,
        "schema_version": SCHEMA_VERSION,
        "storage_format": "parquet",
        "required_datasets": sorted(required),
        "datasets": {name: report.datasets[name] for name in sorted(report.datasets)},
    }
    _write_json_atomic(target, manifest)
    return get_snapshot(sid)


def reopen_snapshot(snapshot_id: date | str, *, confirm: bool = False) -> None:
    """Remove the seal so a snapshot can be changed. Deliberate action only.

    The data files are kept; the snapshot becomes *incomplete* until it is
    sealed again with ``create_snapshot(..., replace=True)``.
    """
    if confirm is not True:
        raise SnapshotExistsError("reopening a sealed snapshot changes research history; pass confirm=True")
    path = manifest_path(snapshot_id)
    if not path.exists():
        raise SnapshotNotFoundError(f"Snapshot {normalize_snapshot_id(snapshot_id)} is not sealed")
    path.unlink()


def verify_snapshot(snapshot_id: date | str) -> ValidationReport:
    """Check a complete snapshot against its manifest (checksums, row counts)."""
    sid = normalize_snapshot_id(snapshot_id)
    manifest = _load_manifest(sid)
    report = ValidationReport(sid)
    for name, meta in manifest["datasets"].items():
        path = snapshot_path(name, sid)
        if not path.is_file():
            report.errors.append(f"{name}: file missing")
        elif _sha256(path) != meta["sha256"]:
            report.errors.append(f"{name}: file changed after the snapshot was sealed (checksum mismatch)")
        else:
            report.datasets[name] = meta
    return report


# --- listing / retrieval -----------------------------------------------------------

def list_snapshots(*, status: Status | None = None) -> list[SnapshotInfo]:
    """All snapshot folders, oldest first. Filter with ``status='complete'`` etc."""
    root = get_data_paths().snapshots
    if not root.is_dir():
        return []
    infos = [_info(p.name) for p in sorted(root.iterdir()) if p.is_dir() and _is_id(p.name)]
    return [i for i in infos if status is None or i.status == status]


def get_snapshot(snapshot_id: date | str) -> SnapshotInfo:
    sid = normalize_snapshot_id(snapshot_id)
    if not snapshot_dir(sid).is_dir():
        raise SnapshotNotFoundError(f"Snapshot {sid} does not exist")
    return _info(sid)


def latest_snapshot() -> SnapshotInfo:
    """Most recent *complete* snapshot."""
    complete = list_snapshots(status="complete")
    if not complete:
        raise SnapshotNotFoundError("No complete snapshot exists yet; create one with create_snapshot()")
    return complete[-1]


def snapshot_exists(snapshot_id: date | str, *, complete: bool = True) -> bool:
    """True if the snapshot exists (and, by default, is complete)."""
    try:
        info = get_snapshot(snapshot_id)
    except SnapshotNotFoundError:
        return False
    return info.status == "complete" if complete else True


def read_snapshot_dataset(
    snapshot_id: date | str, dataset: str, *, require_complete: bool = True
) -> pd.DataFrame:
    """Read one dataset of a snapshot (only from complete snapshots by default)."""
    info = get_snapshot(snapshot_id)
    if require_complete and info.status != "complete":
        raise SnapshotValidationError(info.snapshot_id, [f"snapshot is {info.status}, not complete"])
    spec = get_spec(dataset)
    path = snapshot_path(spec.name, info.snapshot_id)
    if not path.is_file():
        raise DatasetNotFoundError(f"Snapshot {info.snapshot_id} has no {spec.name} dataset")
    return _conform(spec, read_dataset(path), path)


@contextmanager
def snapshot_session(
    snapshot_id: date | str, *, require_complete: bool = True
) -> Iterator[duckdb.DuckDBPyConnection]:
    """In-memory DuckDB session whose ``channels``/``videos``/``comments`` views
    read one snapshot. Works with the ``shared.utils.analytics`` functions via ``con=``.
    """
    info = get_snapshot(snapshot_id)
    if require_complete and info.status != "complete":
        raise SnapshotValidationError(info.snapshot_id, [f"snapshot is {info.status}, not complete"])
    with duckdb_connection(MEMORY) as con:
        for name in info.datasets:
            path = snapshot_path(name, info.snapshot_id).as_posix().replace("'", "''")
            con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{path}')")
        yield con


# --- helpers ---------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _is_id(name: str) -> bool:
    try:
        normalize_snapshot_id(name)
        return True
    except ValueError:
        return False


def _info(sid: str) -> SnapshotInfo:
    folder = snapshot_dir(sid)
    present = tuple(name for name in DATASETS if snapshot_path(name, sid).is_file())
    if not (folder / MANIFEST_NAME).exists():
        return SnapshotInfo(sid, folder, "incomplete", present)
    try:
        manifest = _load_manifest(sid)
        sealed = tuple(n for n in DATASETS if n in manifest["datasets"])  # fixed order
        missing = [n for n in sealed if n not in present]
        created = datetime.fromisoformat(manifest["created_at"].replace("Z", "+00:00"))
        rows = {n: int(m["rows"]) for n, m in manifest["datasets"].items()}
    except (ValueError, KeyError, TypeError) as exc:
        return SnapshotInfo(sid, folder, "invalid", present, problem=f"unreadable manifest: {exc}")
    if missing:
        return SnapshotInfo(sid, folder, "invalid", present, created, rows,
                            problem=f"sealed dataset files missing: {missing}")
    return SnapshotInfo(sid, folder, "complete", sealed, created, rows)


def _load_manifest(sid: str) -> dict[str, Any]:
    path = snapshot_dir(sid) / MANIFEST_NAME
    if not path.exists():
        raise SnapshotNotFoundError(f"Snapshot {sid} is not sealed (no {MANIFEST_NAME})")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("snapshot_id") != sid or "datasets" not in manifest:
        raise ValueError(f"{path} is not a manifest for snapshot {sid}")
    return manifest


def _check_rows(spec, df: pd.DataFrame, sid: str) -> list[str]:
    problems = []
    required = [name for name, f in spec.model.model_fields.items() if f.is_required()]
    for col in required:
        nulls = int(df[col].isna().sum())
        if nulls:
            problems.append(f"{nulls} row(s) missing required '{col}'")
    for col in [c for c in required if c.endswith("_id")]:
        blank = int((df[col].dropna().str.strip() == "").sum())
        if blank:
            problems.append(f"{blank} row(s) with empty '{col}'")

    collected = df[COLLECTED_AT].dropna()
    outside = int((collected.dt.strftime("%Y-%m-%d") != sid).sum())
    if outside:
        problems.append(f"{outside} row(s) whose collected_at is not on {sid} (UTC)")
    dupes = int(df.duplicated(subset=[spec.key, COLLECTED_AT]).sum())
    if dupes:
        problems.append(f"{dupes} duplicate ({spec.key}, collected_at) row(s)")
    for col, dtype in spec.model.DTYPES.items():
        if dtype == "Int64" and (df[col].dropna() < 0).any():
            problems.append(f"negative values in '{col}'")
    return problems


def _dataset_metadata(spec, df: pd.DataFrame, path: Path) -> dict[str, Any]:
    collected = df[COLLECTED_AT]
    return {
        "file": path.name,
        "rows": int(len(df)),
        "unique_ids": int(df[spec.key].nunique()),
        "columns": list(df.columns),
        "collected_at_min": _iso(collected.min()),
        "collected_at_max": _iso(collected.max()),
        "sha256": _sha256(path),
    }


def _iso(value: Any) -> str | None:
    return None if pd.isna(value) else value.isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


# --- research snapshots (full current state at one extraction point) ---------------------

RESEARCH_DIR = "research"
_RESEARCH_ID = re.compile(r"^rs-\d{8}T\d{6}Z$")


@dataclass(frozen=True)
class ResearchSnapshotInfo:
    snapshot_id: str
    path: Path
    created_at: datetime
    source: str
    row_counts: dict[str, int]
    manifest: dict[str, Any]


def research_snapshots_root() -> Path:
    return get_data_paths().snapshots / RESEARCH_DIR


def research_snapshot_dir(snapshot_id: str) -> Path:
    if not isinstance(snapshot_id, str) or not _RESEARCH_ID.fullmatch(snapshot_id):
        raise ValueError(f"invalid research snapshot id {snapshot_id!r}; expected rs-YYYYMMDDTHHMMSSZ")
    return research_snapshots_root() / snapshot_id


def research_dataset_path(snapshot_id: str, dataset: str) -> Path:
    return research_snapshot_dir(snapshot_id) / f"{get_spec(dataset).name}.parquet"


def create_research_snapshot(
    frames: Mapping[str, pd.DataFrame],
    *,
    source: str,
    extracted_at: datetime | None = None,
    details: Mapping[str, Any] | None = None,
) -> ResearchSnapshotInfo:
    """Freeze full datasets (channels, videos, comments) as an immutable research snapshot.

    Frames must have exactly the schema columns. Data is stored as given (not
    deduplicated or repaired) so problems stay visible to validation, with one
    exception: raw commenter ids are refused (privacy), and nothing is written.
    Files are written to a staging folder that is renamed into place only when
    complete, so a failure never leaves a partial snapshot.
    """
    if not _SOURCE.match(source or ""):
        raise ValueError(f"source must be a short lowercase identifier, got {source!r}")
    if set(frames) != set(DATASETS):
        raise ValueError(f"a research snapshot needs exactly {list(DATASETS)}, got {sorted(frames)}")
    for name, df in frames.items():
        expected = list(get_spec(name).model.DTYPES)
        if list(df.columns) != expected:
            raise SchemaError(f"{name}: columns {list(df.columns)} do not match the schema {expected}")
    authors = frames["comments"]["author_channel_id"].dropna()
    raw = sum(1 for a in authors if not privacy.is_pseudonymized(a))
    if raw:
        raise privacy.PrivacyConfigError(
            f"{raw} comment(s) carry commenter ids that are not pseudonyms; refusing to write a research snapshot")

    created = _utcnow()
    sid = "rs-" + created.strftime("%Y%m%dT%H%M%SZ")
    target = research_snapshot_dir(sid)
    if target.exists():
        raise SnapshotExistsError(f"research snapshot {sid} already exists")
    staging = target.with_name(f".{sid}.staging")
    shutil.rmtree(staging, ignore_errors=True)
    try:
        datasets_meta = {}
        for name in DATASETS:
            path = write_dataset(frames[name], staging / f"{name}.parquet")
            datasets_meta[name] = _dataset_metadata(get_spec(name), frames[name], path)
        manifest = {
            "manifest_version": MANIFEST_VERSION,
            "kind": "research",
            "snapshot_id": sid,
            "created_at": _iso(pd.Timestamp(created)),
            "extracted_at": _iso(pd.Timestamp(extracted_at)) if extracted_at else None,
            "source": source,
            "details": dict(details or {}),
            "schema_version": SCHEMA_VERSION,
            "storage_format": "parquet",
            "datasets": datasets_meta,
        }
        _write_json_atomic(staging / MANIFEST_NAME, manifest)
        os.replace(staging, target)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return get_research_snapshot(sid)


def list_research_snapshots() -> list[ResearchSnapshotInfo]:
    """Complete research snapshots, oldest first (folders without a manifest are ignored)."""
    root = research_snapshots_root()
    if not root.is_dir():
        return []
    infos = []
    for p in sorted(root.iterdir()):
        if p.is_dir() and _RESEARCH_ID.fullmatch(p.name) and (p / MANIFEST_NAME).is_file():
            infos.append(get_research_snapshot(p.name))
    return infos


def latest_research_snapshot() -> ResearchSnapshotInfo:
    snaps = list_research_snapshots()
    if not snaps:
        raise SnapshotNotFoundError("no research snapshot exists yet; create one with export_research_snapshot()")
    return snaps[-1]


def get_research_snapshot(snapshot_id: str) -> ResearchSnapshotInfo:
    folder = research_snapshot_dir(snapshot_id)
    path = folder / MANIFEST_NAME
    if not path.is_file():
        raise SnapshotNotFoundError(f"research snapshot {snapshot_id} does not exist")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    return ResearchSnapshotInfo(
        snapshot_id=snapshot_id, path=folder,
        created_at=datetime.fromisoformat(manifest["created_at"].replace("Z", "+00:00")),
        source=manifest["source"],
        row_counts={n: int(m["rows"]) for n, m in manifest["datasets"].items()},
        manifest=manifest,
    )


def verify_research_snapshot(snapshot_id: str) -> ValidationReport:
    """Check every file against the manifest checksum (detects any change after creation)."""
    info = get_research_snapshot(snapshot_id)
    report = ValidationReport(snapshot_id)
    for name, meta in info.manifest["datasets"].items():
        path = info.path / meta["file"]
        if not path.is_file():
            report.errors.append(f"{name}: file missing")
        elif _sha256(path) != meta["sha256"]:
            report.errors.append(f"{name}: file changed after the snapshot was created (checksum mismatch)")
        else:
            report.datasets[name] = meta
    return report
