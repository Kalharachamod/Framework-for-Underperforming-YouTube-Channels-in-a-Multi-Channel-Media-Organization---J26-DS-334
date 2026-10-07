# Shared

Code used by all four components (owned jointly).

- `data_collection/` – YouTube Data API v3 collection and weekly snapshot pipeline
- `schemas/` – common data schema for channels, videos, comments, snapshots
- `utils/` – data paths (`paths.py`), Parquet storage (`parquet_io.py`), DuckDB queries (`duckdb_query.py`); later: hashing of commenter IDs, logging

Data is stored as Parquet and queried with DuckDB; see [docs/architecture/data_layer.md](../docs/architecture/data_layer.md).
