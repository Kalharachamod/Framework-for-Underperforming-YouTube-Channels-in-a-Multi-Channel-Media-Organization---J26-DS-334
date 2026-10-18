"""Test script to verify Supabase PostgreSQL connection for Component 4."""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import psycopg

def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    env_path = Path(__file__).resolve().parent / ".env"
    load_dotenv(env_path, override=True)

    db_url = os.getenv("SUPABASE_DB_URL", "").strip()
    if not db_url:
        print("[!] ERROR: SUPABASE_DB_URL is not set in .env")
        print("    Please add your Supabase database connection string to .env:")
        print("    SUPABASE_DB_URL=postgresql://postgres.kbukuimdsnlcmtkozzuh:[PASSWORD]@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres")
        return 1

    print("[*] Connecting to Supabase PostgreSQL database...")
    try:
        with psycopg.connect(
            db_url,
            sslmode="require",
            connect_timeout=15,
            prepare_threshold=None,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_user, current_database();")
                user, db = cur.fetchone()
                print(f"[+] Connected successfully as user: '{user}' to database: '{db}'")

                # Verify research schema tables
                tables = ["channels", "videos", "channel_stats_history", "video_stats_history"]
                print("\n[*] Checking research schema tables:")
                for table in tables:
                    cur.execute(f"SELECT COUNT(*) FROM research.{table};")
                    count = cur.fetchone()[0]
                    print(f"    - research.{table}: {count:,} records")

                # Inspect video date ranges
                cur.execute("SELECT MIN(published_at), MAX(published_at) FROM research.videos;")
                min_pub, max_pub = cur.fetchone()
                if min_pub and max_pub:
                    print(f"\n[*] Video publication date range: {min_pub} to {max_pub}")

                # Inspect channels summary
                cur.execute("""
                    SELECT c.channel_id, c.channel_name, COUNT(v.video_id) AS video_count
                    FROM research.channels c
                    LEFT JOIN research.videos v ON c.channel_id = v.channel_id
                    GROUP BY c.channel_id, c.channel_name
                    ORDER BY video_count DESC;
                """)
                rows = cur.fetchall()
                print(f"\n[*] Channels in portfolio ({len(rows)} channels):")
                for ch_id, ch_name, count in rows:
                    print(f"    - {ch_name} ({ch_id}): {count} videos")

        print("\n[✓] All database connection and data checks passed!")
        return 0

    except Exception as e:
        print(f"\n[!] Connection failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
