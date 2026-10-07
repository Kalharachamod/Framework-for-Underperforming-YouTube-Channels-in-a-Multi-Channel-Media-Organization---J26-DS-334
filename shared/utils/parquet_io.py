"""Parquet storage: the persistent format of all shared research datasets.

Timestamps are stored in UTC. Naive datetimes are assumed to already be UTC.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Sequence
from pathlib import Path

import pandas as pd

from shared.utils.paths import resolve_path


class DatasetNotFoundError(FileNotFoundError):
    """The requested Parquet dataset does not exist."""


class SchemaError(ValueError):
    """A DataFrame does not match the expected dataset schema."""


def dataset_exists(path: str | os.PathLike[str]) -> bool:
    """True for an existing Parquet file, or a folder containing Parquet files."""
    p = resolve_path(path)
    if p.is_file():
        return True
    return p.is_dir() and any(p.rglob("*.parquet"))


def write_dataset(
    df: pd.DataFrame,
    path: str | os.PathLike[str],
    *,
    overwrite: bool = False,
    required_columns: Iterable[str] | None = None,
) -> Path:
    """Write ``df`` to a Parquet file and return its absolute path.

    Parent folders are created. An existing file is only replaced when
    ``overwrite=True``, and the replacement is atomic: readers never see a
    half-written file.
    """
    target = resolve_path(path)
    if target.suffix != ".parquet":
        raise ValueError(f"Dataset path must end with .parquet: {target}")
    if target.exists() and not overwrite:
        raise FileExistsError(f"Dataset already exists (pass overwrite=True): {target}")

    _check_schema(df, required_columns)
    df = _timestamps_to_utc(df)

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.tmp")
    try:
        df.to_parquet(tmp, engine="pyarrow", index=False)
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    return target


def read_dataset(
    path: str | os.PathLike[str], columns: Sequence[str] | None = None
) -> pd.DataFrame:
    """Read a Parquet file (or a folder of Parquet files) into a DataFrame."""
    source = resolve_path(path)
    if not dataset_exists(source):
        raise DatasetNotFoundError(f"No Parquet dataset at: {source}")
    return pd.read_parquet(source, engine="pyarrow", columns=list(columns) if columns else None)


def _check_schema(df: pd.DataFrame, required_columns: Iterable[str] | None) -> None:
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"Expected a pandas DataFrame, got {type(df).__name__}")
    if df.columns.has_duplicates:
        dupes = sorted(set(df.columns[df.columns.duplicated()]))
        raise SchemaError(f"Duplicate column names: {dupes}")
    if not all(isinstance(c, str) for c in df.columns):
        raise SchemaError("All column names must be strings")
    if required_columns:
        missing = [c for c in required_columns if c not in df.columns]
        if missing:
            raise SchemaError(f"Missing required columns: {missing}")


def _timestamps_to_utc(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        s = out[col]
        if isinstance(s.dtype, pd.DatetimeTZDtype):
            out[col] = s.dt.tz_convert("UTC")
        elif pd.api.types.is_datetime64_dtype(s):
            out[col] = s.dt.tz_localize("UTC")
    return out
