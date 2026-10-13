"""DuckDB: the analytical query engine over the Parquet datasets.

DuckDB is not the source of truth. The database file only holds views and
scratch tables and can be deleted and rebuilt from Parquet at any time.

Relative file paths inside SQL (e.g. ``FROM 'data/processed/x.parquet'``) are
resolved from the project root, whatever the current working directory is.
Sessions use UTC so timestamps match how they are stored.
"""

from __future__ import annotations

import glob
import os
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

import duckdb
import pandas as pd

from shared.utils import paths
from shared.utils.parquet_io import DatasetNotFoundError, dataset_exists

MEMORY = ":memory:"


def connect(
    database: str | os.PathLike[str] | None = None, *, read_only: bool = False
) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection (default: the configured ``DUCKDB_PATH``).

    Pass ``":memory:"`` for a throwaway in-memory database.
    """
    if database is None:
        database = paths.get_data_paths().duckdb
    if str(database) != MEMORY:
        database = paths.resolve_path(database)
        if read_only and not database.exists():
            raise FileNotFoundError(f"DuckDB database not found: {database}")
        database.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(database), read_only=read_only)
    root = paths.PROJECT_ROOT.as_posix().replace("'", "''")
    con.execute(f"SET file_search_path = '{root}'")
    con.execute("SET TimeZone = 'UTC'")
    return con


@contextmanager
def duckdb_connection(
    database: str | os.PathLike[str] | None = None, *, read_only: bool = False
) -> Iterator[duckdb.DuckDBPyConnection]:
    """Context manager that always closes the connection."""
    con = connect(database, read_only=read_only)
    try:
        yield con
    finally:
        con.close()


def query(
    sql: str,
    params: Sequence[Any] | dict[str, Any] | None = None,
    *,
    database: str | os.PathLike[str] | None = None,
) -> pd.DataFrame:
    """Run one SQL statement and return the result as a DataFrame."""
    with duckdb_connection(database) as con:
        return con.execute(sql, params).df()


def query_parquet(
    path: str | os.PathLike[str],
    sql: str = "SELECT * FROM dataset",
    params: Sequence[Any] | dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Query a Parquet file, folder or glob; it is available as the view ``dataset``.

    Runs in memory, so it never locks or changes the DuckDB database file.
    """
    source = paths.resolve_path(path)
    if source.is_dir():
        source = source / "**" / "*.parquet"
    if glob.has_magic(str(source)):
        if not glob.glob(str(source), recursive=True):
            raise DatasetNotFoundError(f"No Parquet files match: {source}")
    elif not dataset_exists(source):
        raise DatasetNotFoundError(f"No Parquet dataset at: {source}")

    with duckdb_connection(MEMORY) as con:
        con.read_parquet(source.as_posix()).create_view("dataset")
        return con.execute(sql, params).df()
