# Data

Raw, processed, snapshot and external data. **Contents are git-ignored** (public YouTube data, hashed commenter IDs; 30-day retention rule applies). Never commit data files.

| Folder | Contents |
|---|---|
| `raw/` | API responses as collected; never edited |
| `snapshots/<YYYY-MM-DD>/` | One research snapshot per UTC collection day; `_snapshot.json` marks it complete and immutable (see [snapshots.md](../docs/architecture/snapshots.md)) |
| `features/` | Model-ready feature tables (Parquet) |
| `processed/<dataset>.parquet` | Latest channels / videos / comments, one row per ID |
| `processed/component_N/` | Component-specific Parquet outputs |
| `research.duckdb` | DuckDB views over the Parquet files; rebuildable (path set by `DUCKDB_PATH`) |

See [docs/architecture/data_layer.md](../docs/architecture/data_layer.md) for the full design.
