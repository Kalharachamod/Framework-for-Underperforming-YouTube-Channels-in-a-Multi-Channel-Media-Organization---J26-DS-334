"""Tests for the Supabase/PostgreSQL research database layer (shared/database/).

Database tests run against a THROWAWAY local PostgreSQL started for the test
session (or TEST_DATABASE_URL), never a real Supabase project. All records are
TEST DATA with synthetic ids; credentials here are fake.
"""

import glob
import os
import shutil
import socket
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

import psycopg
import pytest
from pydantic import ValidationError

from shared.database import connection as dbc
from shared.database import repository as repo
from shared.database.migrate import apply_migrations, applied_versions, migration_files
from shared.database.snapshot_export import export_snapshot_day
from shared.schemas import Channel, Comment, Video
from shared.utils import DuplicateRecordError
from shared.utils import snapshots as snaps
from shared.utils.privacy import is_pseudonymized

FAKE_PASSWORD = "FAKE_pw_never_real_123"
DAY = "2026-09-30"
AT, LATER, EARLIER = f"{DAY}T08:00:00Z", f"{DAY}T20:00:00Z", "2026-09-29T08:00:00Z"


# --- throwaway PostgreSQL ------------------------------------------------------------------

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
        with dbc.connect(f"{base}/c3_template") as c:
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
    conn = dbc.connect(db_url)
    yield conn
    conn.close()


# --- TEST DATA -------------------------------------------------------------------------

def channel(cid="test_ch_a", at=AT, **kw):
    return Channel(**{"channel_id": cid, "channel_name": f"Test {cid}", "subscriber_count": 100,
                      "view_count": 1000, "video_count": 2, "collected_at": at, **kw})


def video(vid="test_v1", cid="test_ch_a", at=AT, **kw):
    return Video(**{"video_id": vid, "channel_id": cid, "title": f"Test {vid}", "description": None,
                    "published_at": "2026-09-01T09:00:00Z", "tags": ["test"], "view_count": 100,
                    "like_count": 10, "comment_count": 1, "collected_at": at, **kw})


def comment(com="test_c1", vid="test_v1", cid="test_ch_a", at=AT, **kw):
    return Comment(**{"comment_id": com, "video_id": vid, "channel_id": cid,
                      "author_channel_id": "UC" + "t" * 22, "comment_text": "Synthetic.",
                      "published_at": "2026-09-02T00:00:00Z", "like_count": 0, "collected_at": at, **kw})


def seed(db):
    repo.upsert_channels(db, [channel(), channel("test_ch_b")])
    repo.upsert_videos(db, [video(), video("test_v2", "test_ch_b")])
    repo.upsert_comments(db, [comment(), comment("test_c2", "test_v2", "test_ch_b", author_channel_id=None)])
    db.commit()


# --- configuration (no database) ------------------------------------------------------------

def test_config_loading(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://testref.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "fake-anon-key")
    monkeypatch.setenv("SUPABASE_DB_URL", f"postgresql://postgres.testref:{FAKE_PASSWORD}@db.example.com:5432/postgres")
    cfg = dbc.load_config()
    assert cfg.url == "https://testref.supabase.co" and cfg.anon_key == "fake-anon-key"
    assert cfg.db_host == "db.example.com"
    assert FAKE_PASSWORD not in repr(cfg) and "fake-anon-key" not in repr(cfg)


@pytest.mark.parametrize("value", [None, "", "postgresql://postgres.your-project-ref:your_db_password@host/postgres"])
def test_missing_or_placeholder_db_url(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    else:
        monkeypatch.setenv("SUPABASE_DB_URL", value)
    with pytest.raises(dbc.DatabaseConfigError, match="SUPABASE_DB_URL is not set"):
        dbc.require_db_url()


def test_wrong_scheme(monkeypatch):
    monkeypatch.setenv("SUPABASE_DB_URL", "mysql://u:p@h/db")
    with pytest.raises(dbc.DatabaseConfigError, match="postgresql://"):
        dbc.require_db_url()


def test_redact_url():
    assert dbc.redact_url(f"postgresql://user:{FAKE_PASSWORD}@h:5432/db") == "postgresql://user:***@h:5432/db"


def test_connection_failure_hides_password():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()  # nothing listens on this port
    with pytest.raises(dbc.DatabaseConnectionError) as err:
        dbc.connect(f"postgresql://postgres:{FAKE_PASSWORD}@127.0.0.1:{port}/postgres")
    assert FAKE_PASSWORD not in str(err.value) and "127.0.0.1" in str(err.value)
    assert err.value.__cause__ is None


# --- schema / migrations ----------------------------------------------------------------

def test_migrations_applied_and_idempotent(db):
    assert applied_versions(db) == {p.stem for p in migration_files()}
    assert apply_migrations(db) == []  # second run does nothing


def test_tables_match_schema_definitions(db):
    """The SQL tables carry exactly the STEP 03 schema fields (+ bookkeeping columns)."""
    for table, model in (("channels", Channel), ("videos", Video), ("comments", Comment)):
        cols = [r[0] for r in db.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema='research' "
            "AND table_name=%s ORDER BY ordinal_position", [table]).fetchall()]
        assert cols == list(model.DTYPES) + ["first_collected_at", "updated_at"], table


def test_row_level_security_enabled(db):
    rows = db.execute("SELECT relname, relrowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                      "WHERE nspname='research' AND relkind='r' AND relname <> 'schema_migrations'").fetchall()
    assert rows and all(enabled for _, enabled in rows)


def test_expected_indexes(db):
    names = {r[0] for r in db.execute("SELECT indexname FROM pg_indexes WHERE schemaname='research'").fetchall()}
    assert {"videos_channel_published_idx", "videos_published_idx", "comments_video_published_idx",
            "comments_channel_idx", "comments_author_idx", "comments_published_idx"} <= names


# --- inserts and reads ---------------------------------------------------------------------

def test_insert_and_get_each_entity(db):
    repo.insert_channel(db, channel())
    repo.insert_video(db, video())
    repo.insert_comment(db, comment())
    db.commit()
    assert repo.get_channel(db, "test_ch_a") == channel()
    assert repo.get_video(db, "test_v1") == video()
    stored = repo.get_comment(db, "test_c1")
    assert is_pseudonymized(stored.author_channel_id)  # raw commenter id never stored
    assert repo.get_channel(db, "test_unknown") is None


def test_insert_duplicate_rejected(db):
    repo.insert_channel(db, channel())
    with pytest.raises(repo.DuplicateKeyError):
        repo.insert_channel(db, channel(at=LATER))
    assert repo.count_rows(db, "channels") == 1


def test_dict_records_validated(db):
    repo.upsert_channels(db, [channel().model_dump()])
    with pytest.raises(ValidationError):
        repo.upsert_channels(db, [{**channel().model_dump(), "subscriber_count": -1}])
    with pytest.raises(ValidationError):
        repo.upsert_channels(db, [{**channel().model_dump(), "collected_at": "2026-09-30 08:00"}])  # naive


def test_lists(db):
    seed(db)
    repo.upsert_videos(db, [video("test_v3", published_at="2026-09-10T00:00:00Z")])
    assert [c.channel_id for c in repo.list_channels(db)] == ["test_ch_a", "test_ch_b"]
    assert [v.video_id for v in repo.list_videos(db, "test_ch_a")] == ["test_v3", "test_v1"]
    assert [c.comment_id for c in repo.list_comments(db, video_id="test_v1")] == ["test_c1"]
    assert [c.comment_id for c in repo.list_comments(db, channel_id="test_ch_b")] == ["test_c2"]
    assert len(repo.list_channels(db, limit=1)) == 1
    with pytest.raises(ValueError):
        repo.list_comments(db)
    with pytest.raises(ValueError):
        repo.list_channels(db, limit=0)


# --- upsert / duplicates ----------------------------------------------------------------

def test_upsert_insert_then_update(db):
    repo.upsert_channels(db, [channel()])
    first = repo.upsert_videos(db, [video(view_count=100)])
    second = repo.upsert_videos(db, [video(at=LATER, view_count=250)])
    assert (first.inserted, first.updated) == (1, 0)
    assert (second.inserted, second.updated) == (0, 1)
    v = repo.get_video(db, "test_v1")
    assert v.view_count == 250 and v.collected_at == datetime(2026, 9, 30, 20, tzinfo=timezone.utc)


def test_history_keeps_every_observation(db):
    repo.upsert_channels(db, [channel()])
    repo.upsert_videos(db, [video(view_count=100)])
    repo.upsert_videos(db, [video(at=LATER, view_count=250)])
    history = repo.stats_history(db, "videos", "test_v1")
    assert [h["view_count"] for h in history] == [100, 250]


def test_older_observation_does_not_overwrite(db):
    repo.upsert_channels(db, [channel(at=LATER, subscriber_count=500)])
    summary = repo.upsert_channels(db, [channel(at=EARLIER, subscriber_count=100)])
    assert (summary.inserted, summary.updated, summary.unchanged_or_older) == (0, 0, 1)
    ch = repo.get_channel(db, "test_ch_a")
    assert ch.subscriber_count == 500
    first = db.execute("SELECT first_collected_at FROM research.channels").fetchone()[0]
    assert first == datetime(2026, 9, 30, 20, tzinfo=timezone.utc)
    assert [h["subscriber_count"] for h in repo.stats_history(db, "channels", "test_ch_a")] == [100, 500]


def test_unchanged_rerun_is_not_an_update(db):
    repo.upsert_channels(db, [channel()])
    s = repo.upsert_channels(db, [channel()])
    assert (s.inserted, s.updated, s.unchanged_or_older) == (0, 0, 1)


def test_batch_duplicates(db):
    repo.upsert_channels(db, [channel()])
    s = repo.upsert_videos(db, [video(), video()])  # exact repeat
    assert s.received == 1 and repo.count_rows(db, "videos") == 1
    with pytest.raises(DuplicateRecordError):
        repo.upsert_videos(db, [video(), video(view_count=999)])  # conflicting versions


def test_newest_in_batch_wins(db):
    repo.upsert_channels(db, [channel()])
    repo.upsert_videos(db, [video(at=LATER, view_count=300), video(at=AT, view_count=100)])
    assert repo.get_video(db, "test_v1").view_count == 300


def test_comment_update(db):
    seed(db)
    s = repo.update_comment(db, [comment(at=LATER, like_count=7)])
    assert s.updated == 1 and repo.get_comment(db, "test_c1").like_count == 7


# --- relationships, constraints, atomicity ---------------------------------------------------

def test_video_requires_existing_channel(db):
    with pytest.raises(repo.ReferentialIntegrityError, match="test_ch_missing"):
        repo.upsert_videos(db, [video(cid="test_ch_missing")])


def test_comment_requires_existing_video(db):
    repo.upsert_channels(db, [channel()])
    with pytest.raises(repo.ReferentialIntegrityError, match="test_v_missing"):
        repo.upsert_comments(db, [comment(vid="test_v_missing")])


def test_batch_is_atomic(db):
    repo.upsert_channels(db, [channel()])
    with pytest.raises(repo.ReferentialIntegrityError):
        repo.upsert_videos(db, [video("test_v1"), video("test_v2", cid="test_ch_missing")])
    assert repo.count_rows(db, "videos") == 0  # nothing from the failed batch


def test_database_rejects_raw_commenter_ids(db):
    seed(db)
    with pytest.raises(psycopg.errors.CheckViolation):
        db.execute("UPDATE research.comments SET author_channel_id = %s", ["UC" + "x" * 22])
    db.rollback()


def test_database_rejects_negative_counts(db):
    repo.upsert_channels(db, [channel()])
    with pytest.raises(psycopg.errors.CheckViolation):
        db.execute("UPDATE research.channels SET view_count = -1")
    db.rollback()


def test_timestamps_round_trip_in_utc(db):
    repo.upsert_channels(db, [channel(at="2026-09-30T13:30:00+05:30")])
    ch = repo.get_channel(db, "test_ch_a")
    assert ch.collected_at == datetime(2026, 9, 30, 8, 0, tzinfo=timezone.utc)
    assert ch.collected_at.utcoffset().total_seconds() == 0


def test_published_and_collected_kept_separate(db):
    seed(db)
    v = repo.get_video(db, "test_v1")
    assert v.published_at == datetime(2026, 9, 1, 9, tzinfo=timezone.utc)
    assert v.collected_at == datetime(2026, 9, 30, 8, tzinfo=timezone.utc)


def test_database_context_manager_rolls_back(db_url):
    with pytest.raises(RuntimeError):
        with dbc.database(db_url) as conn:
            repo.upsert_channels(conn, [channel()])
            raise RuntimeError("boom")
    with dbc.database(db_url) as conn:
        assert repo.count_rows(conn, "channels") == 0


# --- Supabase -> Parquet snapshot -> DuckDB -----------------------------------------------------

def test_export_snapshot_day_and_query_with_duckdb(db, isolated_data_dir):
    seed(db)
    summaries, info = export_snapshot_day(db, DAY, seal=True)
    assert {n: s.snapshot_rows_added for n, s in summaries.items()} == {"channels": 2, "videos": 2, "comments": 2}
    assert info.status == "complete"
    with snaps.snapshot_session(DAY) as con:
        assert con.execute("SELECT count(*) FROM comments WHERE author_channel_id LIKE 'anon_%'").fetchone()[0] == 1
        assert con.execute("SELECT sum(view_count) FROM videos").fetchone()[0] == 200


def test_export_only_takes_that_day(db, isolated_data_dir):
    seed(db)
    repo.upsert_channels(db, [channel("test_ch_c", at="2026-10-01T08:00:00Z")])
    summaries, _ = export_snapshot_day(db, DAY)
    assert summaries["channels"].snapshot_rows_added == 2
    assert not snaps.snapshot_exists("2026-10-01", complete=False)


def test_export_rerun_and_sealed_day(db, isolated_data_dir):
    seed(db)
    export_snapshot_day(db, DAY)
    again, _ = export_snapshot_day(db, DAY)
    assert again["videos"].snapshot_rows_added == 0  # no duplicates
    snaps.create_snapshot(DAY)
    from shared.utils import SnapshotImmutableError
    with pytest.raises(SnapshotImmutableError):
        export_snapshot_day(db, DAY)
