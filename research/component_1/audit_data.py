"""Read-only C1 audit. Run from the repo root: python research/component_1/audit_data.py.

Only aggregate statistics are saved, under the git-ignored results directory.
No collectors, migrations, or source-row exports are used.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
TABLES = ("channels", "videos", "channel_stats_history", "video_stats_history")


def query(cur, statement, params=None):
    cur.execute(statement, params)
    return cur.fetchall()


def inspect_schema(cur):
    """Discover actual columns and primary-key grain before constructing queries."""
    columns = query(cur, """
        SELECT table_name, column_name, data_type, udt_name, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'research' AND table_name = ANY(%s)
        ORDER BY table_name, ordinal_position
    """, (list(TABLES),))
    keys = query(cur, """
        SELECT c.relname AS table_name, a.attname AS column_name
        FROM pg_catalog.pg_index i
        JOIN pg_catalog.pg_class c ON c.oid = i.indrelid
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord)
        JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid AND a.attnum = k.attnum
        WHERE n.nspname = 'research' AND i.indisprimary AND c.relname = ANY(%s)
        ORDER BY c.relname, k.ord
    """, (list(TABLES),))
    return columns, keys


def audit_table(cur, table, columns, keys):
    names = {c["column_name"] for c in columns}
    entity = "channel_id" if table in ("channels", "channel_stats_history") else "video_id"
    intended = [entity, "collected_at"] if table.endswith("_history") else [entity]
    if not set(intended) <= names:
        raise ValueError("Required audit grain columns are unavailable")
    relation = sql.Identifier("research", table)
    result = {"columns": columns, "primary_key": keys, "primary_key_note": "Catalog metadata; an empty list does not establish absence of constraints.", "intended_grain": intended}
    expressions = [sql.SQL("count(*) AS rows")]
    for name in ("channel_id", "video_id"):
        if name in names:
            expressions.append(sql.SQL("count(DISTINCT {}) AS {}").format(
                sql.Identifier(name), sql.Identifier("distinct_" + name)))
    result["counts"] = query(cur, sql.SQL("SELECT {} FROM {}").format(
        sql.SQL(", ").join(expressions), relation))[0]
    result["missing"] = {}
    result["date_ranges"] = {}
    for col in columns:
        name, kind = col["column_name"], col["data_type"]
        identifier = sql.Identifier(name)
        if name.endswith("_id") or "date" in kind or "time" in kind or kind in (
            "bigint", "integer", "smallint", "numeric", "real", "double precision"
        ):
            predicate = sql.SQL("{} IS NULL").format(identifier)
            if kind in ("text", "character varying", "character"):
                predicate = sql.SQL("({} OR btrim({}) = '')").format(predicate, identifier)
            result["missing"][name] = query(cur, sql.SQL(
                "SELECT count(*) AS missing FROM {} WHERE {}"
            ).format(relation, predicate))[0]["missing"]
        if "date" in kind or "time" in kind:
            result["date_ranges"][name] = query(cur, sql.SQL(
                "SELECT min({0}) AS earliest, max({0}) AS latest FROM {1}"
            ).format(identifier, relation))[0]
    grain = sql.SQL(", ").join(map(sql.Identifier, intended))
    result["duplicates"] = query(cur, sql.SQL("""
        SELECT count(*) AS duplicate_groups, coalesce(sum(n - 1), 0) AS excess_rows
        FROM (SELECT count(*) AS n FROM {} GROUP BY {} HAVING count(*) > 1) d
    """).format(relation, grain))[0]
    # Entity summaries contain no source rows or titles; timestamp duplicates are collapsed
    # for cadence so that retries do not masquerade as additional snapshots.
    result["coverage_per_entity"] = query(cur, sql.SQL("""
        WITH observations AS (
            SELECT DISTINCT {entity} AS entity_id, collected_at AS observed_at
            FROM {relation} WHERE collected_at IS NOT NULL AND {entity} IS NOT NULL
        ), intervals AS (
            SELECT *, extract(epoch FROM (observed_at - lag(observed_at)
                OVER (PARTITION BY entity_id ORDER BY observed_at))) / 86400.0 AS gap_days
            FROM observations
        )
        SELECT entity_id, count(*) AS snapshots, count(DISTINCT observed_at::date) AS observed_days, min(observed_at) AS first_observed,
               max(observed_at) AS last_observed,
               extract(epoch FROM (max(observed_at)-min(observed_at)))/86400.0 AS span_days,
               min(gap_days) AS min_gap_days, avg(gap_days) AS mean_gap_days,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY gap_days) AS median_gap_days,
               max(gap_days) AS max_gap_days,
               count(*) FILTER (WHERE gap_days > 1.5) AS gaps_over_1_5_days,
               count(*) FILTER (WHERE gap_days > 7.5) AS gaps_over_7_5_days
        FROM intervals GROUP BY entity_id ORDER BY entity_id
    """).format(entity=sql.Identifier(entity), relation=relation))
    result["snapshots_per_utc_day"] = query(cur, sql.SQL("""
        SELECT collected_at::date AS day, count(*) AS rows,
               count(DISTINCT {}) AS entities
        FROM {} GROUP BY collected_at::date ORDER BY day
    """).format(sql.Identifier(entity), relation))
    return result


def run_audit(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT current_user = 'component1_readonly' AS expected_role, current_setting('transaction_read_only') = 'on' AS read_only")
        access = cur.fetchone()
        if access != {"expected_role": True, "read_only": True}:
            print("Access guard: expected role =", access["expected_role"], "; read-only transaction =", access["read_only"])
            raise ValueError("Expected restricted read-only connection")
        columns, keys = inspect_schema(cur)
        tables = {}
        for table in TABLES:
            cols = [c for c in columns if c["table_name"] == table]
            if not cols:
                raise ValueError("Table schema is unavailable")
            tables[table] = audit_table(cur, table, cols,
                [k["column_name"] for k in keys if k["table_name"] == table])
        # video history has no channel_id: derive channel coverage through the verified video map.
        if {"video_id", "channel_id"} <= {c["column_name"] for c in columns if c["table_name"] == "videos"}:
            tables["video_stats_history"]["channel_mapping"] = query(cur, """
                SELECT count(DISTINCT v.channel_id) AS distinct_channels,
                       count(*) FILTER (WHERE v.video_id IS NULL) AS orphan_history_rows
                FROM research.video_stats_history h
                LEFT JOIN research.videos v ON v.video_id = h.video_id
            """)[0]
    return {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "scope": "Rows visible to component1_readonly; RLS may limit visibility.",
            "cadence_notes": "UTC days; gaps between distinct entity timestamps only. Thresholds are descriptive, not an assumed collection SLA. Leading/trailing missing observations require an external schedule.",
            "tables": tables}


def main():
    phase = "configuration"
    try:
        load_dotenv(ROOT / ".env", override=True)
        url = os.getenv("COMPONENT1_DB_URL", "").strip()
        if not url:
            print("Audit unavailable: COMPONENT1_DB_URL is missing.")
            return 1
        phase = "connection"
        with psycopg.connect(url, sslmode="require", connect_timeout=15,
                prepare_threshold=None, row_factory=dict_row, autocommit=True,
                options="-c default_transaction_read_only=on -c default_transaction_isolation=repeatable\\ read -c statement_timeout=30000 -c lock_timeout=5000 -c idle_in_transaction_session_timeout=60000 -c timezone=UTC") as conn:
            conn.execute("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            conn.execute("SET LOCAL statement_timeout = '30s'")
            conn.execute("SET LOCAL lock_timeout = '5s'")
            conn.execute("SET LOCAL idle_in_transaction_session_timeout = '60s'")
            conn.execute("SET LOCAL TIME ZONE 'UTC'")
            phase = "schema/query audit"
            report = run_audit(conn)
            conn.rollback()
        phase = "local report write"
        directory = ROOT / "research" / "component_1" / "results"
        directory.mkdir(exist_ok=True)
        target = directory / ("audit_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
        target.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
        print("Audit complete. Aggregate report:", target.relative_to(ROOT))
        for name, data in report["tables"].items():
            coverage = data["coverage_per_entity"]
            print(name, data["counts"], "duplicate groups:", data["duplicates"]["duplicate_groups"],
                  "entities with >=3 snapshots:", sum(r["snapshots"] >= 3 for r in coverage))
        return 0
    except Exception as exc:
        # Never disclose driver messages, URLs, credentials, or connection parameters.
        if isinstance(exc, ValueError) and str(exc) in {"Expected restricted read-only connection", "Table schema is unavailable", "Required audit grain columns are unavailable"}:
            print(str(exc))
        category = "database" if isinstance(exc, psycopg.Error) else "configuration/schema/output"
        print("Failure phase:", phase, "category:", category)
        print("Audit failed; no complete report generated. Check configuration, connectivity, permissions, or query timeout. Driver details suppressed.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
