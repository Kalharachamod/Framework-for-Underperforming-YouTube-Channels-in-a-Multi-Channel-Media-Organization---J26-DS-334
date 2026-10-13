"""DuckDB research workspace: one database file to browse and query a snapshot and its results.

Fills the configured DuckDB file (``DUCKDB_PATH``, default ``data/research.duckdb``) with *views* over:

* ``snapshot.*``  the immutable research snapshot (channels, videos, comments),
* ``prepared.*``  the Component 3 prepared datasets (STEP 13),
* one schema per artifact kind (``graph``, ``features``, ``diffusion``, ``topics``, ``embeddings``,
  ``baselines``, ``bridge``, ``evaluation``, ``explanations``) for the newest *complete* run of each
  method (a run is complete when its metadata JSON exists; newest by ``created_at``, as in the API),
* ``workspace.sources`` and ``workspace.info``: which file and run every view reads, and when the
  workspace was built; ``workspace.channel_lookup`` maps the graph node ids used by result files
  (``channel:<channel_id>``) to channel names.

Views hold no data: the Parquet files stay the source of truth, nothing is copied, and the database
can be deleted and rebuilt at any time. A rebuild replaces only the views this module created
(listed in ``workspace.sources``); other objects in the file are left untouched. Paths are absolute
so any DuckDB client (CLI, UI, DBeaver) can read the views.

Privacy: the comment views expose the same pseudonymised commenter ids as the local Parquet files
(raw YouTube ids are never stored). The workspace is a local research file; do not publish it.

Usage::

    python -m research.component_3.duckdb_workspace                 # latest snapshot
    python -m research.component_3.duckdb_workspace --snapshot rs-20261010T081534Z
    python -m research.component_3.duckdb_workspace --ui            # build, then open the DuckDB UI
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from shared.utils import snapshots
from shared.utils.duckdb_query import duckdb_connection
from shared.utils.paths import component_dir, get_data_paths

WORKSPACE_SCHEMA = "workspace"
RUN_KINDS = ("diffusion", "topics", "embeddings", "baselines", "bridge", "evaluation", "explanations")
_RUN_DIR = re.compile(r"^([a-z0-9]+)-[0-9a-f]{12}$")
_NAME = re.compile(r"[^a-z0-9_]+")


@dataclass(frozen=True)
class ViewSource:
    schema: str
    view: str
    path: Path
    run_id: str | None
    created_at: str | None

    @property
    def qualified(self) -> str:
        return f"{self.schema}.{self.view}"


@dataclass(frozen=True)
class WorkspaceSummary:
    database: Path
    snapshot_id: str
    views: list[ViewSource]


class WorkspaceError(RuntimeError):
    """The workspace could not be built (message names the cause, never data values)."""


def _ident(name: str) -> str:
    clean = _NAME.sub("_", name.lower()).strip("_")
    if not clean or clean[0].isdigit():
        clean = f"v_{clean}"
    return clean


def _created_at(run_dir: Path) -> str | None:
    """``created_at`` of the run's metadata JSON, or None when the run has no metadata (incomplete)."""
    for meta in sorted(run_dir.glob("*.json")):
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            return str(data.get("created_at") or "")
    return None


def _latest_runs(kind_dir: Path) -> dict[str, tuple[Path, str]]:
    """Newest complete run per method prefix (``abs``, ``m2v``, ``hgt``…) in an artifact-kind folder."""
    best: dict[str, tuple[Path, str]] = {}
    if not kind_dir.is_dir():
        return best
    for d in sorted(kind_dir.iterdir()):
        m = _RUN_DIR.fullmatch(d.name) if d.is_dir() else None
        if not m:
            continue
        created = _created_at(d)
        if created is None:
            continue
        prefix = m.group(1)
        if prefix not in best or (created, d.name) > (best[prefix][1], best[prefix][0].name):
            best[prefix] = (d, created)
    return best


def discover(snapshot_id: str) -> list[ViewSource]:
    """Every view the workspace would create for ``snapshot_id`` (no database access)."""
    out: list[ViewSource] = []
    snap_dir = snapshots.research_snapshot_dir(snapshot_id)
    for f in sorted(snap_dir.glob("*.parquet")):
        out.append(ViewSource("snapshot", _ident(f.stem), f, snapshot_id, None))

    processed = component_dir(3) / snapshot_id
    for f in sorted(processed.glob("*.parquet")):
        out.append(ViewSource("prepared", _ident(f.stem), f, None, None))

    graph = processed / "graph"
    for f in sorted(graph.glob("*.parquet")):
        out.append(ViewSource("graph", _ident(f.stem), f, None, None))

    features = sorted(d for d in (processed / "features").glob("asof-*") if d.is_dir())
    if features:
        latest = features[-1]
        for f in sorted(latest.glob("*.parquet")):
            out.append(ViewSource("features", _ident(f.stem), f, latest.name, None))

    for kind in RUN_KINDS:
        runs = _latest_runs(processed / kind)
        several = len(runs) > 1
        for prefix, (run_dir, created) in sorted(runs.items()):
            for f in sorted(run_dir.glob("*.parquet")):
                stem = _ident(f.stem)
                # methods sharing a folder (m2v/hgt, louvain/node2vec) get their prefix, without doubling it
                view = f"{prefix}_{stem}" if several and not stem.startswith(prefix) else stem
                out.append(ViewSource(kind, view, f, run_dir.name, created or None))
    return out


def build_workspace(snapshot_id: str | None = None, database: str | Path | None = None) -> WorkspaceSummary:
    """Create or refresh the workspace views for a snapshot (default: the latest one)."""
    if snapshot_id is None:
        snapshot_id = snapshots.latest_research_snapshot().snapshot_id
    else:
        snapshots.get_research_snapshot(snapshot_id)  # validates the id and that the snapshot exists
    views = discover(snapshot_id)
    if not views:
        raise WorkspaceError(f"no Parquet files found for snapshot {snapshot_id}")
    db_path = Path(database) if database is not None else get_data_paths().duckdb

    try:
        with duckdb_connection(db_path) as con:
            _drop_previous(con)
            for schema in sorted({v.schema for v in views} | {WORKSPACE_SCHEMA}):
                con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
            for v in views:
                path = v.path.resolve().as_posix().replace("'", "''")
                con.execute(f"CREATE OR REPLACE VIEW {v.qualified} AS SELECT * FROM read_parquet('{path}')")
            if any(v.qualified == "snapshot.channels" for v in views):
                # result files key channels by graph node id ("channel:<id>"); this maps them to names
                con.execute(f"CREATE OR REPLACE VIEW {WORKSPACE_SCHEMA}.channel_lookup AS "
                            "SELECT 'channel:' || channel_id AS node_id, channel_id, channel_name FROM snapshot.channels")
            con.execute(f"CREATE OR REPLACE TABLE {WORKSPACE_SCHEMA}.sources "
                        "(schema_name VARCHAR, view_name VARCHAR, run_id VARCHAR, created_at VARCHAR, file VARCHAR)")
            con.executemany(f"INSERT INTO {WORKSPACE_SCHEMA}.sources VALUES (?, ?, ?, ?, ?)",
                            [[v.schema, v.view, v.run_id, v.created_at, v.path.resolve().as_posix()] for v in views])
            con.execute(f"CREATE OR REPLACE TABLE {WORKSPACE_SCHEMA}.info "
                        "(snapshot_id VARCHAR, built_at TIMESTAMPTZ, views INTEGER, note VARCHAR)")
            con.execute(f"INSERT INTO {WORKSPACE_SCHEMA}.info VALUES (?, ?, ?, ?)",
                        [snapshot_id, datetime.now(timezone.utc), len(views),
                         "Views over Parquet files; rebuild with python -m research.component_3.duckdb_workspace"])
    except duckdb.IOException as exc:
        raise WorkspaceError(f"the DuckDB file could not be opened for writing ({db_path.name}); "
                             "close other programs using it (DuckDB UI, DBeaver, a notebook) and retry") from exc
    return WorkspaceSummary(db_path, snapshot_id, views)


def _drop_previous(con: duckdb.DuckDBPyConnection) -> None:
    """Drop only the views a previous build created (recorded in workspace.sources)."""
    exists = con.execute("SELECT count(*) FROM information_schema.tables "
                         "WHERE table_schema = ? AND table_name = 'sources'", [WORKSPACE_SCHEMA]).fetchone()[0]
    if not exists:
        return
    for schema, view in con.execute(f"SELECT schema_name, view_name FROM {WORKSPACE_SCHEMA}.sources").fetchall():
        con.execute(f"DROP VIEW IF EXISTS {_ident(schema)}.{_ident(view)}")


def open_ui(database: Path) -> None:  # pragma: no cover - interactive
    """Serve the DuckDB UI for the workspace until Ctrl+C (downloads the ``ui`` extension once)."""
    import time

    with duckdb_connection(database) as con:
        con.execute("INSTALL ui")
        con.execute("LOAD ui")
        url = con.execute("CALL start_ui_server()").fetchone()[0]
        print(f"DuckDB UI: {url}  (open it in your browser; press Ctrl+C to stop)")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            con.execute("CALL stop_ui_server()")


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="duckdb_workspace", description="Build the DuckDB research workspace (views only).")
    ap.add_argument("--snapshot", help="research snapshot id (default: the latest)")
    ap.add_argument("--database", help="DuckDB file (default: DUCKDB_PATH or data/research.duckdb)")
    ap.add_argument("--ui", action="store_true", help="open the DuckDB UI in the browser after building")
    args = ap.parse_args(argv)
    try:
        summary = build_workspace(args.snapshot, args.database)
    except (WorkspaceError, snapshots.SnapshotNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Workspace: {summary.database}\nSnapshot: {summary.snapshot_id}\nViews: {len(summary.views)}")
    for schema in sorted({v.schema for v in summary.views}):
        names = ", ".join(v.view for v in summary.views if v.schema == schema)
        print(f"  {schema}: {names}")
    if args.ui:
        open_ui(summary.database)
    return 0


if __name__ == "__main__":
    sys.exit(main())
