# Shared

Code used by all four components (owned jointly).

- `data_collection/` – YouTube Data API v3 collection and weekly snapshot pipeline
- `schemas/` – validated Channel, Video and Comment schemas and `to_dataframe` (see [docs/architecture/schemas.md](../docs/architecture/schemas.md))
- `utils/` – data paths (`paths.py`), Parquet storage (`parquet_io.py`), DuckDB queries (`duckdb_query.py`), research dataset storage (`datasets.py`, see [docs/architecture/dataset_storage.md](../docs/architecture/dataset_storage.md)); later: hashing of commenter IDs, logging

Data is stored as Parquet and queried with DuckDB; see [docs/architecture/data_layer.md](../docs/architecture/data_layer.md).
