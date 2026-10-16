"""Run explicitly to check Component 1 PostgreSQL access using read-only queries."""

import os
from pathlib import Path

import psycopg
from psycopg import sql
from dotenv import load_dotenv

def main():
    try:
        load_dotenv(Path(__file__).with_name(".env"), override=True)
        db_url = os.getenv("COMPONENT1_DB_URL", "").strip()
        if not db_url:
            raise ValueError("COMPONENT1_DB_URL is missing from your .env file.")

        with psycopg.connect(
            db_url,
            sslmode="require",
            connect_timeout=15,
            options="-c default_transaction_read_only=on",
            prepare_threshold=None,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_user")
                role = cur.fetchone()[0]

                if role != "component1_readonly":
                    raise ValueError(
                        "Expected component1_readonly. Check your .env username."
                    )

                cur.execute("SHOW transaction_read_only")
                if cur.fetchone()[0] != "on":
                    raise ValueError("Expected a read-only transaction.")

                tables = [
                    "channels",
                    "videos",
                    "channel_stats_history",
                    "video_stats_history",
                ]

                for table in tables:
                    query = sql.SQL(
                        "SELECT 1 FROM {}.{} LIMIT 1"
                    ).format(
                        sql.Identifier("research"),
                        sql.Identifier(table),
                    )

                    cur.execute(query)
                    has_data = cur.fetchone() is not None

                    print(
                        f"research.{table}: read passed; "
                        f"data available: {has_data}"
                    )

        print("All four table read tests passed.")

        return 0

    except Exception:
        # Raw driver errors may disclose credentials or connection parameters.
        print("Connection/read test failed. Check configuration, access, and connectivity.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
