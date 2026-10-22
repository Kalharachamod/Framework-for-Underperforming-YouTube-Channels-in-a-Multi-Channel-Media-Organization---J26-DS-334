"""Read-only access to the Component 3 live results published by the nightly job (research.c3_live_*).

The dashboard reads these so it can show last night's bridge scores without the analyst's computer.
Only aggregates exist in these tables (channel ids and names, counts, scores). Connections are read-only.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.services.component_3.service import InvalidParameter, NotFound

RUN_ID = re.compile(r"^live-\d{8}T\d{6}Z$")
CHANNEL_ID = re.compile(r"^[A-Za-z0-9_-]{3,64}$")
RUN_COLUMNS = ["run_id", "started_at", "finished_at", "status", "window_start", "window_end", "snapshot_id",
               "experiment_id", "channels", "videos", "comments", "unique_commenters", "quota_units", "error"]


class LiveUnavailable(RuntimeError):
    """Live results cannot be read (no database configured, unreachable, or tables not created)."""


def _iso(v: Any) -> Any:
    return v.isoformat().replace("+00:00", "Z") if isinstance(v, datetime) else v


DOWN_SECONDS = 60          # after a failed connection, answer from the offline copy for this long
CONNECT_TIMEOUT = 4        # seconds per address; the API must not hang on a blocked network


class LiveResults:
    """Reads the live tables. Each successful answer is also kept as an offline copy (aggregates only), which
    is served, marked ``offline``, when the shared database cannot be reached (for example a network that
    blocks PostgreSQL), so the dashboard still shows the last known live results."""

    def __init__(self, connect: Callable[[], Any] | None = None, cache_dir: Path | None = None):
        self._connect = connect
        if cache_dir is None and connect is None:
            cache_dir = Path(os.getenv("DATA_DIR", "data")) / "cache" / "component_3_live"
        self._cache_dir = cache_dir
        self._down_until = 0.0

    def _cache_path(self, key: str) -> Path | None:
        if self._cache_dir is None:
            return None
        return self._cache_dir / (hashlib.sha256(key.encode()).hexdigest()[:24] + ".json")

    def _cached(self, key: str, compute: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        path = self._cache_path(key)
        if time.monotonic() >= self._down_until:
            try:
                result = compute()
            except LiveUnavailable as exc:
                self._down_until = time.monotonic() + DOWN_SECONDS
                failure = exc
            else:
                if path is not None:
                    try:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        saved = {"saved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "data": result}
                        path.write_text(json.dumps(saved), encoding="utf-8")
                    except OSError:
                        pass
                return result
        else:
            failure = LiveUnavailable("live results are unavailable: the shared database is not reachable "
                                      "from this network")
        if path is not None and path.exists():
            try:
                saved = json.loads(path.read_text(encoding="utf-8"))
                return {**saved["data"], "offline": {"saved_at": saved["saved_at"],
                                                     "reason": "shared database not reachable; showing the last saved copy"}}
            except (OSError, ValueError, KeyError):
                pass
        raise failure

    @contextmanager
    def _conn(self):
        import psycopg

        try:
            if self._connect is not None:
                conn, own = self._connect(), False
            else:
                from shared.database.connection import connect

                conn, own = connect(timeout=CONNECT_TIMEOUT), True
                conn.read_only = True   # the API never writes live results
        except Exception as exc:  # noqa: BLE001 - configuration or network; never echo the URL
            raise LiveUnavailable("live results are unavailable: the shared database is not configured or not "
                                  f"reachable ({type(exc).__name__})") from None
        try:
            yield conn
        except psycopg.errors.UndefinedTable:
            raise LiveUnavailable("live results are not set up yet: run 'python -m shared.database.migrate' "
                                  "and the nightly job") from None
        except psycopg.Error as exc:
            raise LiveUnavailable(f"live results could not be read ({type(exc).__name__})") from None
        finally:
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001
                pass
            if own:
                conn.close()

    def _rows(self, conn, sql: str, params: list | None = None) -> list[dict[str, Any]]:
        cur = conn.execute(sql, params or [])
        cols = [d.name for d in cur.description]
        return [{k: _iso(v) for k, v in zip(cols, r)} for r in cur.fetchall()]

    # --- endpoints -----------------------------------------------------------------------------------

    def runs(self, limit: int = 30) -> dict[str, Any]:
        return self._cached(f"runs|{limit}", lambda: self._runs(limit))

    def _runs(self, limit: int) -> dict[str, Any]:
        with self._conn() as conn:
            items = self._rows(conn, f"SELECT {', '.join(RUN_COLUMNS)} FROM research.c3_live_runs "
                                     "ORDER BY started_at DESC LIMIT %s", [limit])
        latest = next((r for r in items if r["status"] == "completed"), None)
        return {"items": items, "latest_completed_run_id": latest["run_id"] if latest else None,
                "note": "Nightly live monitoring results (rolling window). The frozen thesis results are the "
                        "research snapshots; these update every night."}

    def _run(self, conn, run_id: str | None) -> dict[str, Any]:
        if run_id is not None and not RUN_ID.fullmatch(run_id):
            raise InvalidParameter("run_id must look like live-YYYYMMDDTHHMMSSZ")
        sql = f"SELECT {', '.join(RUN_COLUMNS)} FROM research.c3_live_runs WHERE status = 'completed'"
        rows = self._rows(conn, sql + (" AND run_id = %s" if run_id else " ORDER BY finished_at DESC LIMIT 1"),
                          [run_id] if run_id else [])
        if not rows:
            raise NotFound(f"live run {run_id} does not exist or did not complete" if run_id
                           else "no completed live run yet: the nightly job has not published results")
        return rows[0]

    def bridges(self, run_id: str | None = None, source: str | None = None, limit: int = 100) -> dict[str, Any]:
        if source is not None and not CHANNEL_ID.fullmatch(source):
            raise InvalidParameter("source must be a YouTube channel id")
        if run_id is not None and not RUN_ID.fullmatch(run_id):
            raise InvalidParameter("run_id must look like live-YYYYMMDDTHHMMSSZ")
        return self._cached(f"bridges|{run_id}|{source}|{limit}", lambda: self._bridges(run_id, source, limit))

    def _bridges(self, run_id: str | None, source: str | None, limit: int) -> dict[str, Any]:
        with self._conn() as conn:
            run = self._run(conn, run_id)
            where, params = ["run_id = %s"], [run["run_id"]]
            if source:
                where.append("source_channel_id = %s")
                params.append(source)
            items = self._rows(conn, "SELECT source_channel_id, destination_channel_id, source_channel_name, "
                                     "destination_channel_name, audience_bridge_score, base_score, diffusion_component, "
                                     "embedding_component, topic_component, confidence, shared_commenters, rank, score_status "
                                     f"FROM research.c3_live_bridge_scores WHERE {' AND '.join(where)} "
                                     "ORDER BY audience_bridge_score DESC NULLS LAST, source_channel_id, destination_channel_id "
                                     "LIMIT %s", [*params, limit])
            channels = self._rows(conn, "SELECT channel_id, channel_name, videos, comments, unique_commenters "
                                        "FROM research.c3_live_channels WHERE run_id = %s ORDER BY comments DESC, channel_id",
                                  [run["run_id"]])
            evidence = conn.execute("SELECT count(*) FILTER (WHERE shared_commenters > 0), count(*) "
                                    "FROM research.c3_live_bridge_scores WHERE run_id = %s", [run["run_id"]]).fetchone()
        return {"run": run, "items": items, "channels": channels,
                "pairs_with_evidence": int(evidence[0] or 0), "pairs": int(evidence[1] or 0),
                "note": "Potential audience bridges from public comments in the rolling window; "
                        "not audience migration or causality."}

    def history(self, source: str, destination: str, limit: int = 60) -> dict[str, Any]:
        for v in (source, destination):
            if not CHANNEL_ID.fullmatch(v or ""):
                raise InvalidParameter("source and destination must be YouTube channel ids")
        if source == destination:
            raise InvalidParameter("source and destination must be different channels")
        return self._cached(f"history|{source}|{destination}|{limit}", lambda: self._history(source, destination, limit))

    def _history(self, source: str, destination: str, limit: int) -> dict[str, Any]:
        with self._conn() as conn:
            items = self._rows(conn, "SELECT r.run_id, r.finished_at, b.audience_bridge_score, b.confidence, "
                                     "b.shared_commenters, b.rank FROM research.c3_live_runs r "
                                     "JOIN research.c3_live_bridge_scores b ON b.run_id = r.run_id "
                                     "WHERE r.status = 'completed' AND b.source_channel_id = %s "
                                     "AND b.destination_channel_id = %s ORDER BY r.finished_at DESC LIMIT %s",
                               [source, destination, limit])
        return {"source_channel_id": source, "destination_channel_id": destination, "items": items[::-1]}
