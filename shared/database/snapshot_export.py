"""Supabase -> Parquet research snapshots.

    Supabase current data  ->  export_snapshot_day()  ->  data/snapshots/<day>/*.parquet
                           ->  create_snapshot() (STEP 06: validate + seal)  ->  DuckDB analysis

Research snapshots (``export_research_snapshot``) freeze the FULL current
database state at one consistent extraction point (one repeatable-read,
read-only transaction) as immutable Parquet: the input of Component 3 research.

Snapshot logic (validation, sealing, immutability, manifests) stays in
``shared.utils.snapshots``; this module only reads the database and writes the
day's rows through ``write_snapshot_records``. Nothing is mirrored automatically:
run the export at the end of each collection day, before the next collection
replaces the current rows.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
import psycopg
from psycopg import IsolationLevel

from shared.database import repository
from shared.utils.datasets import DATASETS, StoreSummary, get_spec, write_snapshot_records
from shared.utils.snapshots import (
    ResearchSnapshotInfo,
    SnapshotInfo,
    create_research_snapshot,
    create_snapshot,
    normalize_snapshot_id,
)


def export_snapshot_day(
    conn: psycopg.Connection, snapshot_date: date | str, *, seal: bool = False,
    required: tuple[str, ...] = tuple(DATASETS),
) -> tuple[dict[str, StoreSummary], SnapshotInfo | None]:
    """Write the rows collected on ``snapshot_date`` (UTC) into that day's Parquet snapshot.

    With ``seal=True`` the day is then validated and sealed (``create_snapshot``).
    Re-running before sealing is safe: identical observations are not duplicated.
    """
    day = normalize_snapshot_id(snapshot_date)
    summaries = {name: write_snapshot_records(name, repository.fetch_collected_on(conn, name, day))
                 for name in DATASETS}
    info = create_snapshot(day, required=list(required)) if seal else None
    return summaries, info


def export_research_snapshot(conn: psycopg.Connection) -> ResearchSnapshotInfo:
    """Freeze the full current channels / videos / comments as a research snapshot.

    All three tables are read in one REPEATABLE READ, READ ONLY transaction, so
    they reflect the same moment even if a collector is writing. Only the schema
    columns are exported (commenter ids are already pseudonyms in the database).
    """
    conn.commit()
    previous = (conn.isolation_level, conn.read_only)
    conn.isolation_level, conn.read_only = IsolationLevel.REPEATABLE_READ, True
    try:
        extracted_at = datetime.now(timezone.utc)
        frames = {name: _read_table(conn, name) for name in DATASETS}
        conn.commit()
    finally:
        conn.rollback()
        conn.isolation_level, conn.read_only = previous
    return create_research_snapshot(
        frames, source="supabase_postgresql", extracted_at=extracted_at,
        details={"database_schema": "research", "isolation": "repeatable_read",
                 "tables": {name: f"research.{name}" for name in DATASETS}})


def _read_table(conn: psycopg.Connection, dataset: str) -> pd.DataFrame:
    spec = get_spec(dataset)
    columns = list(spec.model.DTYPES)
    rows = conn.execute(f"SELECT {', '.join(columns)} FROM research.{spec.name} ORDER BY {spec.key}").fetchall()
    return pd.DataFrame(rows, columns=columns).astype(spec.model.DTYPES)
