import glob
import os
import shutil
import socket
import subprocess
import tempfile
import uuid
from urllib.parse import urlsplit

import pandas as pd
import psycopg
import pytest

from shared.database import connection as _dbc
from shared.utils import paths


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Point DATA_DIR and DUCKDB_PATH at a temp folder so tests never touch data/."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "data" / "test.duckdb"))
    # TEST salt only (never a real one); 64 characters like secrets.token_hex(32).
    monkeypatch.setenv("COMMENTER_HASH_SALT", "test-salt-" + "0" * 54)
    return tmp_path / "data"


@pytest.fixture
def project_root(tmp_path, monkeypatch):
    """Use a temp folder as the project root, to test project-relative paths."""
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setattr(paths, "PROJECT_ROOT", root)
    monkeypatch.setenv("DATA_DIR", "data")
    monkeypatch.setenv("DUCKDB_PATH", "data/research.duckdb")
    return root


@pytest.fixture
def videos_df() -> pd.DataFrame:
    """TEST DATA: synthetic records for automated tests only.

    Not real YouTube data. IDs, titles and numbers are invented.
    """
    return pd.DataFrame(
        {
            "channel_id": pd.Series(["test_channel_a", "test_channel_a", "test_channel_b"], dtype="string"),
            "video_id": pd.Series(["test_video_1", "test_video_2", "test_video_3"], dtype="string"),
            "title": pd.Series(["Test video one", "Test video two", None], dtype="string"),
            "view_count": pd.Series([100, 250, 40], dtype="Int64"),
            "like_count": pd.Series([10, pd.NA, 4], dtype="Int64"),
            "engagement_rate": [0.10, 0.08, None],
            "is_short": [False, True, False],
            "published_at": pd.to_datetime(
                ["2026-01-01T10:00:00Z", "2026-01-02T12:30:00Z", "2026-01-03T08:15:00Z"]
            ),
        }
    )


# --- throwaway PostgreSQL (database tests) ---------------------------------------------------
# Never a real Supabase project: a local server created for the test session, or TEST_DATABASE_URL.

def _pg_tool(name):
    found = shutil.which(name)
    if found:
        return found
    hits = sorted(glob.glob(rf"C:\Program Files\PostgreSQL\*\bin\{name}.exe"))
    return hits[-1] if hits else None


@pytest.fixture(scope="session")
def postgres_url():
    url = os.getenv("TEST_DATABASE_URL")
    if url:
        if "supabase" in (urlsplit(url).hostname or ""):
            pytest.fail("TEST_DATABASE_URL must not point at a Supabase project")
        yield url
        return
    initdb, pg_ctl = _pg_tool("initdb"), _pg_tool("pg_ctl")
    if not (initdb and pg_ctl):
        pytest.skip("PostgreSQL server tools (initdb/pg_ctl) not found; install PostgreSQL or set TEST_DATABASE_URL")
    root = tempfile.mkdtemp(prefix="c3pg_")
    data = os.path.join(root, "pg")
    quiet = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "stdin": subprocess.DEVNULL}
    subprocess.run([initdb, "-D", data, "-U", "postgres", "-A", "trust", "-E", "UTF8", "--no-locale"],
                   check=True, timeout=180, **quiet)
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    subprocess.run([pg_ctl, "-D", data, "-o", f"-p {port} -h 127.0.0.1", "-l", os.path.join(root, "log"),
                    "-w", "-t", "60", "start"], check=True, timeout=120, **quiet)
    base = f"postgresql://postgres@127.0.0.1:{port}"
    try:
        with psycopg.connect(f"{base}/postgres", autocommit=True) as c:
            c.execute("CREATE DATABASE c3_template")
        from shared.database.migrate import apply_migrations
        with _dbc.connect(f"{base}/c3_template") as c:
            apply_migrations(c)
        yield base
    finally:
        subprocess.run([pg_ctl, "-D", data, "-m", "fast", "-w", "stop"], timeout=60, **quiet)
        shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def db_url(postgres_url):
    name = "t_" + uuid.uuid4().hex[:12]
    with psycopg.connect(f"{postgres_url}/postgres", autocommit=True) as c:
        c.execute(f"CREATE DATABASE {name} TEMPLATE c3_template")
    yield f"{postgres_url}/{name}"
    with psycopg.connect(f"{postgres_url}/postgres", autocommit=True) as c:
        c.execute(f"DROP DATABASE {name} WITH (FORCE)")


@pytest.fixture
def db(db_url):
    conn = _dbc.connect(db_url)
    yield conn
    conn.close()
