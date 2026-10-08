"""Apply the SQL migrations in shared/database/migrations/ in order.

    python -m shared.database.migrate          # apply pending migrations
    python -m shared.database.migrate status   # list applied / pending

Each file runs in its own transaction and is recorded in
research.schema_migrations, so running the command again is safe.
"""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg

from shared.database.connection import DatabaseConfigError, DatabaseConnectionError, connect, load_config

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))


def applied_versions(conn: psycopg.Connection) -> set[str]:
    _ensure_table(conn)
    return {row[0] for row in conn.execute("SELECT version FROM research.schema_migrations").fetchall()}


def apply_migrations(conn: psycopg.Connection) -> list[str]:
    """Apply pending migrations; returns the versions applied now."""
    done = applied_versions(conn)
    conn.commit()
    applied = []
    for path in migration_files():
        version = path.stem
        if version in done:
            continue
        try:
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO research.schema_migrations (version) VALUES (%s)", [version])
            conn.commit()
        except psycopg.Error:
            conn.rollback()
            raise
        applied.append(version)
    return applied


def _ensure_table(conn: psycopg.Connection) -> None:
    conn.execute("CREATE SCHEMA IF NOT EXISTS research")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS research.schema_migrations (
            version    text PRIMARY KEY,
            applied_at timestamptz NOT NULL DEFAULT now()
        )""")


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    try:
        cfg = load_config()
        with connect() as conn:
            print(f"Database: {cfg.db_host}")
            if args[:1] == ["status"]:
                done = applied_versions(conn)
                for path in migration_files():
                    print(f"  {'applied' if path.stem in done else 'PENDING'}  {path.stem}")
                return 0
            applied = apply_migrations(conn)
            print("Applied: " + (", ".join(applied) if applied else "nothing (database is up to date)"))
            return 0
    except (DatabaseConfigError, DatabaseConnectionError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except psycopg.Error as exc:
        print(f"Migration failed: {type(exc).__name__}: {str(exc).splitlines()[0]}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
