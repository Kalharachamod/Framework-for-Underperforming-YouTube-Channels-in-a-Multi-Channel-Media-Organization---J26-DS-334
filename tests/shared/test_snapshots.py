"""Tests for research snapshot management (shared/utils/snapshots.py).

All records are TEST DATA: synthetic IDs, names and text invented for testing.
They are not real YouTube channels, videos, comments or commenters.
"""

import json
from datetime import date, datetime, timezone

import pandas as pd
import pytest

from shared.schemas import SCHEMA_VERSION, Channel, Comment, Video, to_dataframe
from shared.utils import SnapshotImmutableError, store_records, write_dataset
from shared.utils import analytics as a
from shared.utils import snapshots as s
from shared.utils.datasets import snapshot_path

DAY1, DAY2 = "2026-10-07", "2026-10-08"


# --- TEST DATA ------------------------------------------------------------------------

def _channel(cid, day, subs=100):
    return Channel(channel_id=cid, channel_name=f"Test {cid}", subscriber_count=subs,
                   view_count=1000, video_count=2, collected_at=f"{day}T08:00:00Z")


def _video(vid, cid, day, views=100):
    return Video(video_id=vid, channel_id=cid, title=f"Test {vid}", published_at="2026-10-01T09:00:00Z",
                 tags=["test"], view_count=views, like_count=5, comment_count=1,
                 collected_at=f"{day}T08:30:00Z")


def _comment(com, vid, cid, day, author="test_author_1"):
    return Comment(comment_id=com, video_id=vid, channel_id=cid, author_channel_id=author,
                   comment_text="Synthetic test comment.", published_at="2026-10-02T10:00:00Z",
                   like_count=0, collected_at=f"{day}T09:00:00Z")


def collect_day(day, views=100, with_comments=True):
    """Simulate one collection day using store_records (no API calls)."""
    store_records("channels", [_channel("test_ch_a", day), _channel("test_ch_b", day, subs=None)])
    store_records("videos", [_video("test_v1", "test_ch_a", day, views), _video("test_v2", "test_ch_b", day)])
    if with_comments:
        store_records("comments", [_comment("test_c1", "test_v1", "test_ch_a", day),
                                   _comment("test_c2", "test_v2", "test_ch_b", day, author=None)])


# --- create ---------------------------------------------------------------------

def test_create_snapshot(isolated_data_dir):
    collect_day(DAY1)
    info = s.create_snapshot(DAY1)

    assert info.snapshot_id == DAY1
    assert info.status == "complete"
    assert info.path == isolated_data_dir / "snapshots" / DAY1
    assert info.datasets == ("channels", "videos", "comments")
    assert info.row_counts == {"channels": 2, "videos": 2, "comments": 2}
    assert (info.path / "_snapshot.json").is_file()


def test_snapshot_directory_and_dataset_files(isolated_data_dir):
    collect_day(DAY1)
    s.create_snapshot(DAY1)
    folder = isolated_data_dir / "snapshots" / DAY1
    assert sorted(p.name for p in folder.iterdir()) == [
        "_snapshot.json", "channels.parquet", "comments.parquet", "videos.parquet",
    ]


@pytest.mark.parametrize("dataset, model, key, ids", [
    ("channels", Channel, "channel_id", ["test_ch_a", "test_ch_b"]),
    ("videos", Video, "video_id", ["test_v1", "test_v2"]),
    ("comments", Comment, "comment_id", ["test_c1", "test_c2"]),
])
def test_each_dataset_readable_from_snapshot(isolated_data_dir, dataset, model, key, ids):
    collect_day(DAY1)
    s.create_snapshot(DAY1)
    df = s.read_snapshot_dataset(DAY1, dataset)
    assert list(df.columns) == list(model.DTYPES)
    assert sorted(df[key]) == ids


def test_nullable_values_kept_in_snapshot(isolated_data_dir):
    collect_day(DAY1)
    s.create_snapshot(DAY1)
    ch = s.read_snapshot_dataset(DAY1, "channels").set_index("channel_id")
    assert pd.isna(ch.loc["test_ch_b", "subscriber_count"])
    com = s.read_snapshot_dataset(DAY1, "comments").set_index("comment_id")
    assert pd.isna(com.loc["test_c2", "author_channel_id"])


# --- metadata -------------------------------------------------------------------

def test_manifest_metadata(isolated_data_dir, monkeypatch):
    monkeypatch.setattr(s, "_utcnow", lambda: datetime(2026, 10, 7, 23, 0, tzinfo=timezone.utc))
    collect_day(DAY1)
    s.create_snapshot(DAY1)
    manifest = json.loads(s.manifest_path(DAY1).read_text(encoding="utf-8"))

    assert manifest["snapshot_id"] == DAY1
    assert manifest["created_at"] == "2026-10-07T23:00:00Z"
    assert manifest["source"] == "youtube_data_api"
    assert manifest["schema_version"] == SCHEMA_VERSION
    assert manifest["storage_format"] == "parquet"
    assert manifest["required_datasets"] == ["channels", "comments", "videos"]
    videos = manifest["datasets"]["videos"]
    assert videos["rows"] == 2 and videos["unique_ids"] == 2
    assert videos["columns"] == list(Video.DTYPES)
    assert videos["collected_at_min"] == "2026-10-07T08:30:00Z"
    assert len(videos["sha256"]) == 64


def test_manifest_has_no_secrets_or_commenter_ids(isolated_data_dir, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "TEST_KEY_SHOULD_NOT_APPEAR")
    monkeypatch.setenv("COMMENTER_HASH_SALT", "TEST_SALT_SHOULD_NOT_APPEAR_" + "0" * 40)
    collect_day(DAY1)
    s.create_snapshot(DAY1)
    text = s.manifest_path(DAY1).read_text(encoding="utf-8")
    for secret in ("TEST_KEY_SHOULD_NOT_APPEAR", "TEST_SALT_SHOULD_NOT_APPEAR", "test_author_1"):
        assert secret not in text


def test_custom_source_validated(isolated_data_dir):
    collect_day(DAY1)
    assert s.create_snapshot(DAY1, source="synthetic_test").status == "complete"
    collect_day(DAY2)
    with pytest.raises(ValueError):
        s.create_snapshot(DAY2, source="Bad Source!")


# --- listing and retrieval ---------------------------------------------------------

def test_list_snapshots_sorted_with_status(isolated_data_dir):
    collect_day(DAY2)
    collect_day(DAY1)
    s.create_snapshot(DAY1)
    (isolated_data_dir / "snapshots" / "not-a-date").mkdir()  # ignored

    infos = s.list_snapshots()
    assert [(i.snapshot_id, i.status) for i in infos] == [(DAY1, "complete"), (DAY2, "incomplete")]
    assert [i.snapshot_id for i in s.list_snapshots(status="complete")] == [DAY1]
    assert infos[1].datasets == ("channels", "videos", "comments")  # present, not yet sealed


def test_list_snapshots_when_none(isolated_data_dir):
    assert s.list_snapshots() == []


def test_latest_snapshot_is_latest_complete(isolated_data_dir):
    collect_day(DAY1)
    collect_day(DAY2)
    s.create_snapshot(DAY1)
    assert s.latest_snapshot().snapshot_id == DAY1  # DAY2 is still incomplete
    s.create_snapshot(DAY2)
    assert s.latest_snapshot().snapshot_id == DAY2


def test_latest_snapshot_none_complete(isolated_data_dir):
    collect_day(DAY1)
    with pytest.raises(s.SnapshotNotFoundError):
        s.latest_snapshot()


def test_get_snapshot_by_date_or_string(isolated_data_dir):
    collect_day(DAY1)
    s.create_snapshot(DAY1)
    assert s.get_snapshot(date(2026, 10, 7)) == s.get_snapshot(DAY1)
    with pytest.raises(s.SnapshotNotFoundError):
        s.get_snapshot("2026-01-01")


def test_snapshot_exists(isolated_data_dir):
    collect_day(DAY1)
    assert not s.snapshot_exists(DAY1)             # incomplete
    assert s.snapshot_exists(DAY1, complete=False)
    s.create_snapshot(DAY1)
    assert s.snapshot_exists(DAY1)
    assert not s.snapshot_exists(DAY2)


@pytest.mark.parametrize("bad", ["07-10-2026", "2026-13-01", "2026-10-07T00:00", "../etc", "", None, 20261007])
def test_invalid_snapshot_ids(isolated_data_dir, bad):
    with pytest.raises(ValueError):
        s.normalize_snapshot_id(bad)


def test_datetime_is_not_a_snapshot_id():
    with pytest.raises(ValueError):
        s.normalize_snapshot_id(datetime(2026, 10, 7, tzinfo=timezone.utc))


# --- immutability -------------------------------------------------------------------

def test_duplicate_snapshot_protection(isolated_data_dir):
    collect_day(DAY1)
    s.create_snapshot(DAY1)
    before = s.manifest_path(DAY1).read_bytes()
    with pytest.raises(s.SnapshotExistsError, match="replace=True"):
        s.create_snapshot(DAY1)
    assert s.manifest_path(DAY1).read_bytes() == before


def test_sealed_snapshot_rejects_new_writes(isolated_data_dir):
    collect_day(DAY1)
    s.create_snapshot(DAY1)
    files = {p: p.read_bytes() for p in (isolated_data_dir / "snapshots" / DAY1).iterdir()}
    latest_before = (isolated_data_dir / "processed" / "videos.parquet").read_bytes()

    with pytest.raises(SnapshotImmutableError, match=DAY1):
        store_records("videos", [_video("test_v1", "test_ch_a", DAY1, views=999)])

    assert {p: p.read_bytes() for p in (isolated_data_dir / "snapshots" / DAY1).iterdir()} == files
    assert (isolated_data_dir / "processed" / "videos.parquet").read_bytes() == latest_before


def test_later_days_still_writable_after_seal(isolated_data_dir):
    collect_day(DAY1)
    s.create_snapshot(DAY1)
    collect_day(DAY2, views=500)  # new day: allowed
    assert s.get_snapshot(DAY2).status == "incomplete"


def test_explicit_reopen_and_replace(isolated_data_dir):
    collect_day(DAY1)
    s.create_snapshot(DAY1)
    with pytest.raises(s.SnapshotExistsError):
        s.reopen_snapshot(DAY1)  # confirm flag required

    s.reopen_snapshot(DAY1, confirm=True)
    assert s.get_snapshot(DAY1).status == "incomplete"
    store_records("videos", [_video("test_v3", "test_ch_a", DAY1)])  # deliberate correction
    info = s.create_snapshot(DAY1, replace=True)
    assert info.row_counts["videos"] == 3


def test_verify_detects_modified_files(isolated_data_dir):
    collect_day(DAY1)
    s.create_snapshot(DAY1)
    assert s.verify_snapshot(DAY1).ok

    # Bypass the storage layer to simulate tampering or an accidental edit.
    path = snapshot_path("videos", DAY1)
    df = s.read_snapshot_dataset(DAY1, "videos")
    df.loc[0, "view_count"] = 123456
    write_dataset(df, path, overwrite=True)

    report = s.verify_snapshot(DAY1)
    assert not report.ok
    assert "checksum mismatch" in report.errors[0]


# --- validation and incomplete snapshots ---------------------------------------------

def test_incomplete_snapshot_detected(isolated_data_dir):
    collect_day(DAY1, with_comments=False)
    report = s.validate_snapshot(DAY1)
    assert not report.ok
    assert report.errors == ["comments: missing comments.parquet"]

    with pytest.raises(s.SnapshotValidationError, match="comments"):
        s.create_snapshot(DAY1)
    assert not s.manifest_path(DAY1).exists()
    assert s.get_snapshot(DAY1).status == "incomplete"


def test_required_subset_allows_partial_collections(isolated_data_dir):
    collect_day(DAY1, with_comments=False)
    info = s.create_snapshot(DAY1, required=["channels", "videos"])
    assert info.status == "complete"
    assert info.datasets == ("channels", "videos")


def test_invalid_required_argument(isolated_data_dir):
    collect_day(DAY1)
    with pytest.raises(ValueError):
        s.create_snapshot(DAY1, required=["playlists"])
    with pytest.raises(ValueError):
        s.create_snapshot(DAY1, required=[])


def test_create_snapshot_for_day_without_data(isolated_data_dir):
    with pytest.raises(s.SnapshotNotFoundError):
        s.create_snapshot(DAY1)


def test_unreadable_parquet_fails_validation(isolated_data_dir):
    collect_day(DAY1)
    snapshot_path("comments", DAY1).write_bytes(b"not a parquet file")
    report = s.validate_snapshot(DAY1)
    assert not report.ok and "comments: Cannot read" in report.errors[0]
    with pytest.raises(s.SnapshotValidationError):
        s.create_snapshot(DAY1)


def test_wrong_schema_fails_validation(isolated_data_dir):
    collect_day(DAY1)
    write_dataset(pd.DataFrame({"channel_id": ["test_ch_a"]}), snapshot_path("channels", DAY1), overwrite=True)
    report = s.validate_snapshot(DAY1)
    assert any("does not match the Channel schema" in e for e in report.errors)


def test_row_level_problems_reported(isolated_data_dir):
    collect_day(DAY1)
    bad = to_dataframe([_video("test_v1", "test_ch_a", DAY1), _video("test_v2", "test_ch_a", DAY2)], Video)
    bad.loc[0, "channel_id"] = pd.NA            # missing required id
    write_dataset(bad, snapshot_path("videos", DAY1), overwrite=True)

    errors = s.validate_snapshot(DAY1).errors
    assert any("missing required 'channel_id'" in e for e in errors)
    assert any("collected_at is not on 2026-10-07" in e for e in errors)  # timestamp in wrong day


def test_invalid_manifest_reported(isolated_data_dir):
    collect_day(DAY1)
    s.manifest_path(DAY1).write_text("{ not json", encoding="utf-8")
    info = s.get_snapshot(DAY1)
    assert info.status == "invalid" and "unreadable manifest" in info.problem
    assert not s.snapshot_exists(DAY1)
    with pytest.raises(s.SnapshotNotFoundError):
        s.latest_snapshot()


def test_missing_sealed_file_marks_invalid(isolated_data_dir):
    collect_day(DAY1)
    s.create_snapshot(DAY1)
    snapshot_path("comments", DAY1).unlink()
    info = s.get_snapshot(DAY1)
    assert info.status == "invalid" and "comments" in info.problem


def test_reading_incomplete_snapshot_requires_opt_in(isolated_data_dir):
    collect_day(DAY1)
    with pytest.raises(s.SnapshotValidationError, match="incomplete"):
        s.read_snapshot_dataset(DAY1, "videos")
    assert len(s.read_snapshot_dataset(DAY1, "videos", require_complete=False)) == 2


def test_failed_manifest_write_leaves_no_complete_snapshot(isolated_data_dir, monkeypatch):
    collect_day(DAY1)

    def boom(*args, **kwargs):
        raise OSError("disk full (simulated)")

    monkeypatch.setattr(s.os, "replace", boom)
    with pytest.raises(OSError, match="simulated"):
        s.create_snapshot(DAY1)
    folder = isolated_data_dir / "snapshots" / DAY1
    assert not (folder / "_snapshot.json").exists()
    assert not any(p.name.endswith(".tmp") for p in folder.iterdir())  # temp file cleaned up
    assert s.get_snapshot(DAY1).status == "incomplete"


# --- timestamps -------------------------------------------------------------------

def test_timestamps_utc_in_snapshot(isolated_data_dir):
    store_records("videos", [Video(video_id="test_v1", channel_id="test_ch_a", title="t",
                                   published_at="2026-10-01T14:30:00+05:30",
                                   collected_at="2026-10-07T05:00:00+05:30")])  # 2026-10-06 23:30 UTC
    assert s.get_snapshot("2026-10-06").datasets == ("videos",)
    s.create_snapshot("2026-10-06", required=["videos"])
    v = s.read_snapshot_dataset("2026-10-06", "videos").iloc[0]
    assert v["collected_at"] == pd.Timestamp("2026-10-06 23:30", tz="UTC")
    assert v["published_at"] == pd.Timestamp("2026-10-01 09:00", tz="UTC")


def test_created_at_is_utc(isolated_data_dir):
    collect_day(DAY1)
    info = s.create_snapshot(DAY1)
    assert info.created_at.utcoffset().total_seconds() == 0


# --- DuckDB -----------------------------------------------------------------------

def test_duckdb_query_against_snapshot(isolated_data_dir):
    collect_day(DAY1, views=100)
    collect_day(DAY2, views=250)
    s.create_snapshot(DAY1)
    s.create_snapshot(DAY2)

    with s.snapshot_session(DAY1) as con:
        assert con.execute("SELECT view_count FROM videos WHERE video_id = 'test_v1'").fetchone()[0] == 100
        assert a.count_channels(con=con) == 2  # analytics functions work on a snapshot
        assert a.get_video_comments("test_v1", con=con)["comment_id"].tolist() == ["test_c1"]

    with s.snapshot_session(DAY2) as con:
        assert con.execute("SELECT view_count FROM videos WHERE video_id = 'test_v1'").fetchone()[0] == 250


def test_snapshot_session_requires_complete(isolated_data_dir):
    collect_day(DAY1)
    with pytest.raises(s.SnapshotValidationError):
        with s.snapshot_session(DAY1):
            pass
    with s.snapshot_session(DAY1, require_complete=False) as con:
        assert con.execute("SELECT count(*) FROM comments").fetchone()[0] == 2


def test_history_view_spans_snapshots(isolated_data_dir):
    collect_day(DAY1, views=100)
    collect_day(DAY2, views=250)
    got = a.run_query(
        "SELECT view_count FROM videos_history WHERE video_id = ? ORDER BY collected_at", ["test_v1"]
    )
    assert got["view_count"].tolist() == [100, 250]
