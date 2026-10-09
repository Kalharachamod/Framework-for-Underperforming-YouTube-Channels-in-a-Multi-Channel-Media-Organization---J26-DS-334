"""Read-only data access to Component 3 research snapshots and persisted artifacts.

The API never recomputes research results. It reads:
* research snapshots (immutable Parquet, STEP 12) for channel metadata,
* processed artifacts under data/processed/component_3/<snapshot_id>/ (STEPs 13-22),
with bounded DuckDB queries over single Parquet files (projection, WHERE, LIMIT/OFFSET), so a
request never loads all comments or embeddings into memory.

Folder names mirror the research modules (verified by tests): graph/, features/asof-*/,
diffusion/ppr-*, topics/top-*, baselines/louvain-*|node2vec-*, bridge/abs-*, evaluation/eval-*,
explanations/xpl-*.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from shared.utils import snapshots
from shared.utils.duckdb_query import MEMORY, duckdb_connection
from shared.utils.paths import component_dir

GRAPH_DIR, FEATURES_DIR, DIFFUSION_DIR, TOPICS_DIR = "graph", "features", "diffusion", "topics"
BASELINES_DIR, BRIDGE_DIR, EVALUATION_DIR, EXPLANATIONS_DIR = "baselines", "bridge", "evaluation", "explanations"
BRIDGE_RUN, EVALUATION_META, EXPLANATION_META = "bridge_run.json", "evaluation_run_metadata.json", \
    "explanation_run_metadata.json"
_ARTIFACT_ID = re.compile(r"^[a-z0-9]+-[0-9a-f]{12}$")


class StorageError(RuntimeError):
    """A storage read failed (message is safe to log; never contains data values)."""


class SnapshotMissing(LookupError):
    pass


@dataclass(frozen=True)
class SnapshotRef:
    snapshot_id: str
    created_at: datetime
    extracted_at: datetime | None
    row_counts: dict[str, int]

    @property
    def as_of(self) -> datetime:
        return self.extracted_at or self.created_at


class Component3Store:
    """Thin, read-only access layer. All methods are bounded and side-effect free."""

    # --- snapshots -------------------------------------------------------------------------------

    def list_snapshots(self) -> list[SnapshotRef]:
        try:
            infos = snapshots.list_research_snapshots()
        except (OSError, ValueError) as exc:
            raise StorageError(f"research snapshots could not be listed ({type(exc).__name__})") from None
        return [_ref(i) for i in infos]

    def snapshot(self, snapshot_id: str | None) -> SnapshotRef:
        """A given snapshot, or the latest one when ``snapshot_id`` is None."""
        snaps = self.list_snapshots()
        if not snaps:
            raise SnapshotMissing("no research snapshot exists yet")
        if snapshot_id is None:
            return snaps[-1]
        for s in snaps:
            if s.snapshot_id == snapshot_id:
                return s
        raise SnapshotMissing(f"research snapshot {snapshot_id} does not exist")

    def snapshot_dataset(self, snapshot_id: str, dataset: str) -> Path:
        return snapshots.research_dataset_path(snapshot_id, dataset)

    # --- artifact locations ------------------------------------------------------------------------

    def processed_dir(self, snapshot_id: str) -> Path:
        return component_dir(3) / snapshot_id

    def features_dir(self, snap: SnapshotRef) -> Path:
        tag = "asof-" + snap.as_of.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return self.processed_dir(snap.snapshot_id) / FEATURES_DIR / tag

    def runs(self, snapshot_id: str, kind: str, prefix: str, meta_file: str) -> list[dict[str, Any]]:
        """Metadata of complete runs (``meta_file`` present), oldest first by created_at."""
        root = self.processed_dir(snapshot_id) / kind
        if not root.is_dir():
            return []
        out = []
        for d in root.iterdir():
            if d.is_dir() and d.name.startswith(prefix + "-") and _ARTIFACT_ID.fullmatch(d.name):
                meta = self.read_json(d / meta_file)
                if meta is not None:
                    out.append({**meta, "_dir": d})
        return sorted(out, key=lambda m: (str(m.get("created_at", "")), m["_dir"].name))

    def count_dirs(self, snapshot_id: str, kind: str, prefix: str = "") -> int:
        root = self.processed_dir(snapshot_id) / kind
        if not root.is_dir():
            return 0
        return sum(1 for d in root.iterdir() if d.is_dir() and not d.name.startswith(".") and d.name.startswith(prefix))

    @staticmethod
    def read_json(path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise StorageError(f"artifact metadata could not be read ({type(exc).__name__})") from None

    # --- bounded Parquet queries -----------------------------------------------------------------

    def query(self, path: Path, columns: Sequence[str] | None = None, where: str = "", params: Sequence[Any] = (),
              order_by: str = "", limit: int | None = None, offset: int = 0) -> pd.DataFrame:
        """SELECT <columns> FROM read_parquet(path) [WHERE] [ORDER BY] [LIMIT/OFFSET]; values are bound
        parameters, identifiers come only from code (never from requests)."""
        if not path.is_file():
            raise FileNotFoundError(path.name)
        cols = ", ".join(_ident(c) for c in columns) if columns else "*"
        sql = f"SELECT {cols} FROM read_parquet(?)"
        if where:
            sql += f" WHERE {where}"
        if order_by:
            sql += f" ORDER BY {order_by}"
        if limit is not None:
            sql += f" LIMIT {int(limit)} OFFSET {int(offset)}"
        try:
            with duckdb_connection(MEMORY) as con:
                return con.execute(sql, [path.as_posix(), *params]).df()
        except (duckdb.Error, OSError) as exc:
            raise StorageError(f"artifact query failed ({type(exc).__name__})") from None

    def count(self, path: Path, where: str = "", params: Sequence[Any] = ()) -> int:
        if not path.is_file():
            raise FileNotFoundError(path.name)
        sql = "SELECT count(*) FROM read_parquet(?)" + (f" WHERE {where}" if where else "")
        try:
            with duckdb_connection(MEMORY) as con:
                return int(con.execute(sql, [path.as_posix(), *params]).fetchone()[0])
        except (duckdb.Error, OSError) as exc:
            raise StorageError(f"artifact query failed ({type(exc).__name__})") from None

    def columns(self, path: Path) -> list[str]:
        try:
            with duckdb_connection(MEMORY) as con:
                return [r[0] for r in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [path.as_posix()]).fetchall()]
        except (duckdb.Error, OSError) as exc:
            raise StorageError(f"artifact query failed ({type(exc).__name__})") from None


def _ref(info) -> SnapshotRef:
    m = info.manifest
    ext = m.get("extracted_at")
    return SnapshotRef(info.snapshot_id, info.created_at,
                       datetime.fromisoformat(ext.replace("Z", "+00:00")).astimezone(timezone.utc) if ext else None,
                       dict(info.row_counts))


def _ident(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError(f"invalid column name {name!r}")
    return f'"{name}"'
