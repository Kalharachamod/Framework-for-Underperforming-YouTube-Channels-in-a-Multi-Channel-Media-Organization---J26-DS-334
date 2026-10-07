# Shared

Code used by all four components (owned jointly).

- `data_collection/` – YouTube Data API v3 client (`youtube_client.py`) and organization channel discovery (`org_discovery.py`, CLI `discover.py`, see [docs/architecture/org_discovery.md](../docs/architecture/org_discovery.md)); collectors come later
- `schemas/` – validated Channel, Video and Comment schemas and `to_dataframe` (see [docs/architecture/schemas.md](../docs/architecture/schemas.md))
- `utils/` – data paths (`paths.py`), Parquet storage (`parquet_io.py`), DuckDB queries (`duckdb_query.py`), research dataset storage (`datasets.py`, see [docs/architecture/dataset_storage.md](../docs/architecture/dataset_storage.md)), analytical queries (`analytics.py`, see [docs/architecture/analytics.md](../docs/architecture/analytics.md)), research snapshots (`snapshots.py`, see [docs/architecture/snapshots.md](../docs/architecture/snapshots.md)); later: hashing of commenter IDs, logging

Data is stored as Parquet and queried with DuckDB; see [docs/architecture/data_layer.md](../docs/architecture/data_layer.md).
