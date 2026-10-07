"""Storage of the shared research datasets (channels, videos, comments).

Connects the schemas in ``shared.schemas`` to the Parquet layer. Every dataset
is kept in two forms:

* **Snapshots** (history, append-only):
  ``data/snapshots/<YYYY-MM-DD>/<dataset>.parquet``. Every observation is kept;
  a record is identified by ``(id, collected_at)``. The folder date is the UTC
  date of ``collected_at``.
* **Latest** (current state, upserted): ``data/processed/<dataset>.parquet``.
  One row per id: the observation with the newest ``collected_at``.

``collected_at`` is when our system observed a record; ``published_at`` is when
YouTube published it. Only ``collected_at`` decides which observation is newer.

Single writer assumed: run one collector at a time.

A snapshot day sealed by ``shared.utils.snapshots.create_snapshot`` (it holds a
``_snapshot.json`` manifest) is immutable: ``store_records`` refuses to write to it.
"""

from __future__ import annotations

import glob
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from shared.schemas import Channel, Comment, ResearchRecord, Video, to_dataframe
from shared.utils.parquet_io import SchemaError, read_dataset, write_dataset
from shared.utils import paths
from shared.utils.paths import get_data_paths, snapshot_dir


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    model: type[ResearchRecord]
    key: str


DATASETS: dict[str, DatasetSpec] = {
    "channels": DatasetSpec("channels", Channel, "channel_id"),
    "videos": DatasetSpec("videos", Video, "video_id"),
    "comments": DatasetSpec("comments", Comment, "comment_id"),
}

COLLECTED_AT = "collected_at"
MANIFEST_NAME = "_snapshot.json"


class DuplicateRecordError(ValueError):
    """One batch holds two different versions of the same record at the same collected_at."""


class SnapshotImmutableError(RuntimeError):
    """A write would change a sealed (complete) snapshot."""


def is_sealed(snapshot_date: date | str) -> bool:
    """True when the snapshot day has been sealed by ``create_snapshot``."""
    return (snapshot_dir(snapshot_date) / MANIFEST_NAME).exists()


@dataclass
class StoreSummary:
    dataset: str
    received: int
    snapshot_files: list[Path] = field(default_factory=list)
    snapshot_rows_added: int = 0
    latest_path: Path | None = None
    latest_inserted: int = 0
    latest_updated: int = 0


def get_spec(dataset: str) -> DatasetSpec:
    try:
        return DATASETS[dataset]
    except KeyError:
        raise ValueError(f"Unknown dataset {dataset!r}; expected one of {sorted(DATASETS)}") from None


def latest_path(dataset: str) -> Path:
    return get_data_paths().processed / f"{get_spec(dataset).name}.parquet"


def snapshot_path(dataset: str, snapshot_date: date | str) -> Path:
    return snapshot_dir(snapshot_date) / f"{get_spec(dataset).name}.parquet"


def history_glob(dataset: str) -> Path:
    return get_data_paths().snapshots / "*" / f"{get_spec(dataset).name}.parquet"


# --- writing -------------------------------------------------------------------

def store_records(dataset: str, records: Iterable[ResearchRecord | Mapping[str, Any]]) -> StoreSummary:
    """Validate records, append them to their snapshots and upsert the latest table.

    Records may be schema instances or dicts (validated here). Nothing is written
    if any record is invalid or the existing latest table is unreadable. Re-running
    the same batch is safe: it produces the same files.
    """
    spec = get_spec(dataset)
    batch = _validated_frame(spec, records)
    summary = StoreSummary(dataset=spec.name, received=len(batch))
    if batch.empty:
        return summary
    snap_dates = batch[COLLECTED_AT].dt.strftime("%Y-%m-%d")
    sealed = sorted(day for day in snap_dates.unique() if is_sealed(day))
    if sealed:
        raise SnapshotImmutableError(
            f"{spec.name}: snapshot(s) {sealed} are sealed and cannot be changed; "
            "use reopen_snapshot(..., confirm=True) to change one deliberately"
        )
    existing_latest = _read_conformed(spec, latest_path(spec.name))

    for day, rows in batch.groupby(snap_dates, sort=True):
        path, added = _append_snapshot(spec, snapshot_path(spec.name, day), rows)
        summary.snapshot_files.append(path)
        summary.snapshot_rows_added += added

    summary.latest_path, summary.latest_inserted, summary.latest_updated = _upsert_latest(
        spec, batch, existing_latest
    )
    return summary


def _validated_frame(spec: DatasetSpec, records: Iterable[ResearchRecord | Mapping[str, Any]]) -> pd.DataFrame:
    """Validate, drop exact repeats, and reject conflicting versions of one observation."""
    unique: dict[tuple[str, str], ResearchRecord] = {}
    conflicts: set[str] = set()
    for record in records:
        if not isinstance(record, ResearchRecord):
            record = spec.model.model_validate(record)
        elif not isinstance(record, spec.model):
            raise TypeError(f"{spec.name} expects {spec.model.__name__}, got {type(record).__name__}")
        ident = (getattr(record, spec.key), getattr(record, COLLECTED_AT).isoformat())
        seen = unique.get(ident)
        if seen is not None and seen != record:
            conflicts.add(ident[0])
        unique[ident] = record
    if conflicts:
        raise DuplicateRecordError(
            f"{spec.name}: different records share the same {spec.key} and collected_at: {sorted(conflicts)}"
        )
    return to_dataframe(unique.values(), spec.model)


def _append_snapshot(spec: DatasetSpec, path: Path, rows: pd.DataFrame) -> tuple[Path, int]:
    """Add observations to one snapshot file; existing observations are kept."""
    existing = _read_conformed(spec, path)
    if existing is None:
        return write_dataset(rows, path), len(rows)

    combined = _concat(existing, rows)
    # Re-collecting the same observation (id + collected_at) replaces it; the rest is kept.
    combined = combined.drop_duplicates(subset=[spec.key, COLLECTED_AT], keep="last")
    combined = combined.sort_values([COLLECTED_AT, spec.key], kind="stable")
    write_dataset(combined, path, overwrite=True)
    return path, len(combined) - len(existing)


def _upsert_latest(
    spec: DatasetSpec, batch: pd.DataFrame, existing: pd.DataFrame | None
) -> tuple[Path, int, int]:
    """Keep one row per id: newest collected_at wins; on a tie the newer write wins."""
    path = latest_path(spec.name)
    old_ids = set() if existing is None else set(existing[spec.key])

    combined = batch if existing is None else _concat(existing, batch)
    combined = combined.sort_values(COLLECTED_AT, kind="stable")
    latest = combined.drop_duplicates(subset=[spec.key], keep="last").sort_values(spec.key)

    incoming = set(batch[spec.key])
    inserted = len(incoming - old_ids)
    updated = 0
    if existing is not None:
        before, after = _fingerprints(existing, spec.key), _fingerprints(latest, spec.key)
        updated = sum(before[i] != after[i] for i in incoming & old_ids)

    write_dataset(latest, path, overwrite=True)
    return path, inserted, updated


# --- reading -------------------------------------------------------------------

def read_latest(dataset: str) -> pd.DataFrame:
    """Current state: one row per id."""
    spec = get_spec(dataset)
    return _conform(spec, read_dataset(latest_path(spec.name)), latest_path(spec.name))


def read_snapshot(dataset: str, snapshot_date: date | str) -> pd.DataFrame:
    spec = get_spec(dataset)
    path = snapshot_path(spec.name, snapshot_date)
    return _conform(spec, read_dataset(path), path)


def read_history(dataset: str) -> pd.DataFrame:
    """Every stored observation across all snapshots, ordered by collected_at."""
    spec = get_spec(dataset)
    days = sorted(p.parent.name for p in get_data_paths().snapshots.glob(f"*/{spec.name}.parquet"))
    frames = [read_snapshot(spec.name, d) for d in days]
    if not frames:
        return to_dataframe([], spec.model)
    history = _concat(*frames).sort_values([COLLECTED_AT, spec.key], kind="stable")
    return history.reset_index(drop=True)


def create_views(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Create DuckDB views over the stored Parquet datasets.

    ``<dataset>`` reads the latest table, ``<dataset>_history`` all snapshots.
    Views store project-relative paths, so the database file works on any machine.
    Returns the names of the views created (datasets with no files are skipped).
    """
    created = []
    for name in DATASETS:
        for view, path in {name: latest_path(name), f"{name}_history": history_glob(name)}.items():
            if not glob.glob(str(path)):
                continue
            con.execute(f"CREATE OR REPLACE VIEW {view} AS SELECT * FROM read_parquet('{_sql_path(path)}')")
            created.append(view)
    return created


# --- helpers -------------------------------------------------------------------

def _read_conformed(spec: DatasetSpec, path: Path) -> pd.DataFrame | None:
    if not path.is_file():
        return None
    return _conform(spec, read_dataset(path), path)


def _conform(spec: DatasetSpec, df: pd.DataFrame, path: str | os.PathLike[str]) -> pd.DataFrame:
    """Check a stored file matches the current schema and restore schema dtypes."""
    expected = list(spec.model.DTYPES)
    if list(df.columns) != expected:
        missing = [c for c in expected if c not in df.columns]
        extra = [c for c in df.columns if c not in expected]
        raise SchemaError(
            f"{path} does not match the {spec.model.__name__} schema "
            f"(missing: {missing}, unexpected: {extra})"
        )
    df = df.copy()
    for col, dtype in spec.model.DTYPES.items():
        if isinstance(dtype, pd.ArrowDtype):
            df[col] = df[col].map(lambda v: None if v is None else list(v))
    return df.astype(spec.model.DTYPES).reset_index(drop=True)


def _concat(*frames: pd.DataFrame) -> pd.DataFrame:
    return pd.concat(frames, ignore_index=True)


def _fingerprints(df: pd.DataFrame, key: str) -> dict[str, tuple]:
    """Hashable, NA-safe representation of each row, by id."""
    def norm(value: Any) -> Any:
        if isinstance(value, (list, tuple, np.ndarray)):
            return tuple(value)
        return None if pd.isna(value) else value

    return {
        row[key]: tuple(norm(v) for v in row.values())
        for row in df.astype(object).to_dict("records")
    }


def _sql_path(path: Path) -> str:
    """Project-relative path when possible (resolved via DuckDB's file_search_path)."""
    try:
        text = path.relative_to(paths.PROJECT_ROOT).as_posix()
    except ValueError:
        text = path.as_posix()
    return text.replace("'", "''")
