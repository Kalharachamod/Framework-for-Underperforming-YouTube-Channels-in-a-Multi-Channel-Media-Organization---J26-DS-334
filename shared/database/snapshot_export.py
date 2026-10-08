"""Supabase -> Parquet research snapshots.

    Supabase current data  ->  export_snapshot_day()  ->  data/snapshots/<day>/*.parquet
                           ->  create_snapshot() (STEP 06: validate + seal)  ->  DuckDB analysis

Snapshot logic (validation, sealing, immutability, manifests) stays in
``shared.utils.snapshots``; this module only reads the database and writes the
day's rows through ``write_snapshot_records``. Nothing is mirrored automatically:
run the export at the end of each collection day, before the next collection
replaces the current rows.
"""

from __future__ import annotations

from datetime import date

import psycopg

from shared.database import repository
from shared.utils.datasets import DATASETS, StoreSummary, write_snapshot_records
from shared.utils.snapshots import SnapshotInfo, create_snapshot, normalize_snapshot_id


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
