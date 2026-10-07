# Shared

Code used by all four components (owned jointly).

- `data_collection/` – YouTube Data API v3 collection and weekly snapshot pipeline
- `schemas/` – common data schema for channels, videos, comments, snapshots
- `utils/` – hashing of commenter IDs, logging, helpers

Data is stored as Parquet and queried with DuckDB; see [docs/architecture/data_layer.md](../docs/architecture/data_layer.md).
