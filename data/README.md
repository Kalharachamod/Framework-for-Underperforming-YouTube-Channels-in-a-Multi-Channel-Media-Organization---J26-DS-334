# Data

Raw, processed, snapshot and external data. **Contents are git-ignored** (public YouTube data, hashed commenter IDs; 30-day retention rule applies). Never commit data files.

| Folder | Contents |
|---|---|
| `raw/` | API responses as collected; never edited |
| `snapshots/` | Normalised Parquet tables, one partition per `snapshot_date` (shared by all components) |
| `features/` | Model-ready feature tables (Parquet) |
| `processed/component_N/` | Component-specific Parquet outputs |
| `research.duckdb` | DuckDB views over the Parquet files; rebuildable (path set by `DUCKDB_PATH`) |

See [docs/architecture/data_layer.md](../docs/architecture/data_layer.md) for the full design.
