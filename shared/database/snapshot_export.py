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

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
from typing import Any

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


def export_research_snapshot(conn: psycopg.Connection, *, scope: Mapping[str, Sequence[str]] | None = None,
                             channel_ids: Sequence[str] | None = None,
                             source: str = "supabase_postgresql",
                             details: Mapping[str, Any] | None = None) -> ResearchSnapshotInfo:
    """Freeze the current channels / videos / comments as a research snapshot.

    All three tables are read in one REPEATABLE READ, READ ONLY transaction, so
    they reflect the same moment even if a collector is writing. Only the schema
    columns are exported (commenter ids are already pseudonyms in the database).

    ``scope`` optionally restricts the export to given ids per dataset, e.g.
    ``{"channels": [...], "videos": [...], "comments": [...]}`` for a pilot; datasets
    not named in ``scope`` are exported in full. The scope is recorded in the manifest.

    ``channel_ids`` optionally restricts all three datasets to those channels (their videos and
    comments), so data of other organizations stored in the same database never enters the snapshot.
    """
    scope = {k: sorted(set(v)) for k, v in (scope or {}).items()}
    unknown = sorted(set(scope) - set(DATASETS))
    if unknown:
        raise ValueError(f"unknown dataset(s) in scope: {unknown}")
    conn.commit()
    previous = (conn.isolation_level, conn.read_only)
    conn.isolation_level, conn.read_only = IsolationLevel.REPEATABLE_READ, True
    try:
        extracted_at = datetime.now(timezone.utc)
        channels = sorted(set(channel_ids)) if channel_ids is not None else None
        frames = {name: _read_table(conn, name, scope.get(name), channels) for name in DATASETS}
        conn.commit()
    finally:
        conn.rollback()
        conn.isolation_level, conn.read_only = previous
    return create_research_snapshot(
        frames, source=source, extracted_at=extracted_at,
        details={"database_schema": "research", "isolation": "repeatable_read",
                 "tables": {name: f"research.{name}" for name in DATASETS},
                 "scope": {name: len(ids) for name, ids in scope.items()} or "full tables",
                 **({"channel_filter": len(channels)} if channels is not None else {}),
                 **dict(details or {})})


def _read_table(conn: psycopg.Connection, dataset: str, ids: Sequence[str] | None = None,
                channel_ids: Sequence[str] | None = None) -> pd.DataFrame:
    spec = get_spec(dataset)
    columns = list(spec.model.DTYPES)
    clauses, params = [], []
    if ids is not None:
        clauses.append(f"{spec.key} = ANY(%s)")
        params.append(list(ids))
    if channel_ids is not None:  # every research table carries channel_id
        clauses.append("channel_id = ANY(%s)")
        params.append(list(channel_ids))
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(f"SELECT {', '.join(columns)} FROM research.{spec.name}{where} ORDER BY {spec.key}",
                        params).fetchall()
    return pd.DataFrame(rows, columns=columns).astype(spec.model.DTYPES)
