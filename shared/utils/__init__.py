"""Shared helpers: data paths, Parquet storage and DuckDB queries."""

from shared.utils.duckdb_query import connect, duckdb_connection, query, query_parquet
from shared.utils.parquet_io import (
    DatasetNotFoundError,
    SchemaError,
    dataset_exists,
    read_dataset,
    write_dataset,
)
from shared.utils.paths import (
    PROJECT_ROOT,
    component_dir,
    get_data_paths,
    resolve_path,
    snapshot_dir,
)

__all__ = [
    "PROJECT_ROOT",
    "DatasetNotFoundError",
    "SchemaError",
    "component_dir",
    "connect",
    "dataset_exists",
    "duckdb_connection",
    "get_data_paths",
    "query",
    "query_parquet",
    "read_dataset",
    "resolve_path",
    "snapshot_dir",
    "write_dataset",
]
