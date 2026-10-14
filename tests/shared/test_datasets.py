"""Tests for schema -> Parquet dataset storage (shared/utils/datasets.py).

All records are TEST DATA: synthetic IDs, names and text invented for testing.
They are not real YouTube channels, videos, comments or commenters.
"""

from datetime import datetime, timezone

import pandas as pd
import pytest
from pydantic import ValidationError

from shared.schemas import Channel, Comment, Video
from shared.utils import (
    DatasetReadError,
    DuplicateRecordError,
    SchemaError,
    create_views,
    duckdb_connection,
    get_data_paths,
    latest_path,
    read_history,
    read_latest,
    read_snapshot,
    snapshot_path,
    store_records,
    write_dataset,
)

DAY1 = "2026-10-07T08:00:00Z"
DAY1_LATER = "2026-10-07T20:00:00Z"
DAY2 = "2026-10-08T08:00:00Z"


# --- TEST DATA builders ----------------------------------------------------------

def channel(cid="test_channel_a", collected_at=DAY1, **kw) -> Channel:
    data = {"channel_id": cid, "channel_name": f"Test {cid}", "subscriber_count": 100,
            "view_count": 1000, "video_count": 10, "collected_at": collected_at}
    return Channel(**{**data, **kw})


def video(vid="test_video_1", cid="test_channel_a", collected_at=DAY1, **kw) -> Video:
    data = {"video_id": vid, "channel_id": cid, "title": f"Test {vid}", "description": None,
            "published_at": "2026-10-01T09:00:00Z", "tags": ["test"], "view_count": 100,
            "like_count": 10, "comment_count": 2, "collected_at": collected_at}
    return Video(**{**data, **kw})


def comment(com="test_comment_1", vid="test_video_1", cid="test_channel_a", collected_at=DAY1, **kw) -> Comment:
    data = {"comment_id": com, "video_id": vid, "channel_id": cid, "author_channel_id": "test_author_1",
            "comment_text": "Synthetic test comment.", "published_at": "2026-10-02T10:00:00Z",
            "like_count": 0, "collected_at": collected_at}
    return Comment(**{**data, **kw})


# --- storing and reading each dataset -------------------------------------------

@pytest.mark.parametrize(
    "dataset, records, model",
    [
        ("channels", [channel(), channel("test_channel_b")], Channel),
        ("videos", [video(), video("test_video_2")], Video),
        ("comments", [comment(), comment("test_comment_2")], Comment),
    ],
)
def test_store_and_read_each_dataset(isolated_data_dir, dataset, records, model):
    summary = store_records(dataset, records)

    assert summary.received == 2
    assert summary.snapshot_rows_added == 2
    assert summary.latest_inserted == 2 and summary.latest_updated == 0
    assert summary.latest_path == isolated_data_dir / "processed" / f"{dataset}.parquet"
    assert summary.snapshot_files == [isolated_data_dir / "snapshots" / "2026-10-07" / f"{dataset}.parquet"]

    for df in (read_latest(dataset), read_snapshot(dataset, "2026-10-07"), read_history(dataset)):
        assert len(df) == 2
        assert list(df.columns) == list(model.DTYPES)
        assert {c: str(t) for c, t in df.dtypes.items()} == {c: str(t) for c, t in model.DTYPES.items()}


def test_dict_records_are_validated(isolated_data_dir):
    store_records("channels", [channel().model_dump()])
    assert read_latest("channels").loc[0, "channel_id"] == "test_channel_a"


def test_nullable_fields_survive(isolated_data_dir):
    store_records("videos", [video(description=None, like_count=None, comment_count=None, tags=[])])
    store_records("comments", [comment(author_channel_id=None, like_count=None)])

    v = read_latest("videos").iloc[0]
    assert pd.isna(v["description"]) and pd.isna(v["like_count"]) and pd.isna(v["comment_count"])
    assert list(v["tags"]) == []
    c = read_latest("comments").iloc[0]
    assert pd.isna(c["author_channel_id"]) and pd.isna(c["like_count"])


def test_tags_round_trip(isolated_data_dir):
    store_records("videos", [video(tags=["a", "b"]), video("test_video_2", tags=[])])
    df = read_latest("videos").set_index("video_id")
    assert list(df.loc["test_video_1", "tags"]) == ["a", "b"]
    assert list(df.loc["test_video_2", "tags"]) == []


def test_timestamps_are_utc_and_exact(isolated_data_dir):
    store_records("videos", [video(published_at="2026-10-01T14:30:00+05:30", collected_at="2026-10-07T13:30:00+05:30")])
    row = read_latest("videos").iloc[0]
    assert row["published_at"] == pd.Timestamp("2026-10-01 09:00:00", tz="UTC")
    assert row["collected_at"] == pd.Timestamp("2026-10-07 08:00:00", tz="UTC")
    assert row["published_at"] != row["collected_at"]


def test_read_back_validates_against_schema(isolated_data_dir):
    original = video(tags=["x"])
    store_records("videos", [original])
    row = read_latest("videos").iloc[0].to_dict()
    assert Video(**{**row, "tags": list(row["tags"])}) == original


# --- duplicates -------------------------------------------------------------------

@pytest.mark.parametrize(
    "dataset, make, key",
    [("channels", channel, "channel_id"), ("videos", video, "video_id"), ("comments", comment, "comment_id")],
)
def test_exact_repeat_in_batch_stored_once(isolated_data_dir, dataset, make, key):
    summary = store_records(dataset, [make(), make()])
    assert summary.received == 1
    assert read_latest(dataset)[key].tolist() == [make().model_dump()[key]]
    assert len(read_history(dataset)) == 1


@pytest.mark.parametrize(
    "dataset, make, changed",
    [
        ("channels", channel, {"subscriber_count": 999}),
        ("videos", video, {"view_count": 999}),
        ("videos", video, {"tags": ["different"]}),
        ("comments", comment, {"like_count": 7}),
    ],
)
def test_conflicting_versions_of_same_observation_rejected(isolated_data_dir, dataset, make, changed):
    with pytest.raises(DuplicateRecordError, match="same"):
        store_records(dataset, [make(), make(**changed)])
    assert not latest_path(dataset).exists()  # nothing written


@pytest.mark.parametrize(
    "dataset, make, key, metric",
    [
        ("channels", channel, "channel_id", "subscriber_count"),
        ("videos", video, "video_id", "view_count"),
        ("comments", comment, "comment_id", "like_count"),
    ],
)
def test_newer_observation_updates_latest_and_keeps_history(isolated_data_dir, dataset, make, key, metric):
    store_records(dataset, [make(**{metric: 1})])
    summary = store_records(dataset, [make(collected_at=DAY2, **{metric: 50})])

    assert summary.latest_inserted == 0 and summary.latest_updated == 1
    latest = read_latest(dataset)
    assert len(latest) == 1
    assert latest.loc[0, metric] == 50
    assert latest.loc[0, "collected_at"] == pd.Timestamp(DAY2)

    history = read_history(dataset)
    assert history[metric].tolist() == [1, 50]
    assert history[key].nunique() == 1


def test_older_observation_does_not_replace_newer(isolated_data_dir):
    store_records("videos", [video(collected_at=DAY2, view_count=500)])
    summary = store_records("videos", [video(collected_at=DAY1, view_count=100)])  # late, older data

    assert summary.latest_updated == 0
    assert read_latest("videos").loc[0, "view_count"] == 500
    assert sorted(read_history("videos")["view_count"]) == [100, 500]


def test_recollecting_same_observation_replaces_it(isolated_data_dir):
    store_records("videos", [video(view_count=100)])
    summary = store_records("videos", [video(view_count=101)])  # same id + collected_at: a correction

    assert summary.snapshot_rows_added == 0
    assert summary.latest_updated == 1
    assert read_history("videos")["view_count"].tolist() == [101]


def test_unchanged_rerun_reports_no_updates(isolated_data_dir):
    store_records("channels", [channel()])
    summary = store_records("channels", [channel()])
    assert (summary.snapshot_rows_added, summary.latest_inserted, summary.latest_updated) == (0, 0, 0)


# --- incremental storage ---------------------------------------------------------

def test_incremental_runs(isolated_data_dir):
    first = store_records("videos", [video("test_video_1"), video("test_video_2")])
    second = store_records("videos", [video("test_video_2", collected_at=DAY2, view_count=300),
                                      video("test_video_3", collected_at=DAY2)])

    assert (first.latest_inserted, first.latest_updated) == (2, 0)
    assert (second.latest_inserted, second.latest_updated) == (1, 1)
    latest = read_latest("videos").set_index("video_id")
    assert sorted(latest.index) == ["test_video_1", "test_video_2", "test_video_3"]
    assert latest.loc["test_video_1", "view_count"] == 100  # untouched record preserved
    assert latest.loc["test_video_2", "view_count"] == 300
    assert len(read_history("videos")) == 4


def test_empty_batch_writes_nothing(isolated_data_dir):
    summary = store_records("comments", [])
    assert summary.received == 0
    assert not latest_path("comments").exists()


# --- snapshots ---------------------------------------------------------------------

def test_snapshots_by_collection_date(isolated_data_dir):
    store_records("channels", [channel(collected_at=DAY1)])
    store_records("channels", [channel(collected_at=DAY2, subscriber_count=150)])

    snaps = get_data_paths().snapshots
    assert sorted(p.name for p in snaps.iterdir()) == ["2026-10-07", "2026-10-08"]
    assert read_snapshot("channels", "2026-10-07").loc[0, "subscriber_count"] == 100
    assert read_snapshot("channels", "2026-10-08").loc[0, "subscriber_count"] == 150


def test_second_run_same_day_appends_to_snapshot(isolated_data_dir):
    store_records("videos", [video(collected_at=DAY1, view_count=100)])
    store_records("videos", [video(collected_at=DAY1_LATER, view_count=180)])

    day = read_snapshot("videos", "2026-10-07")
    assert day["view_count"].tolist() == [100, 180]
    assert read_latest("videos").loc[0, "view_count"] == 180


def test_other_snapshots_are_not_rewritten(isolated_data_dir):
    store_records("videos", [video(collected_at=DAY1)])
    day1 = snapshot_path("videos", "2026-10-07")
    before = (day1.stat().st_mtime_ns, day1.read_bytes())

    store_records("videos", [video(collected_at=DAY2, view_count=200)])
    assert (day1.stat().st_mtime_ns, day1.read_bytes()) == before


def test_batch_spanning_midnight_split_by_utc_date(isolated_data_dir):
    summary = store_records("comments", [
        comment("test_comment_1", collected_at="2026-10-07T23:59:00Z"),
        comment("test_comment_2", collected_at="2026-10-08T00:01:00Z"),
    ])
    assert [p.parent.name for p in summary.snapshot_files] == ["2026-10-07", "2026-10-08"]


def test_published_at_does_not_choose_snapshot(isolated_data_dir):
    store_records("videos", [video(published_at="2020-01-01T00:00:00Z", collected_at=DAY1)])
    assert snapshot_path("videos", "2026-10-07").is_file()
    assert not (get_data_paths().snapshots / "2020-01-01").exists()


# --- DuckDB --------------------------------------------------------------------

@pytest.fixture
def stored(isolated_data_dir):
    store_records("channels", [channel("test_channel_a"), channel("test_channel_b", subscriber_count=None)])
    store_records("videos", [
        video("test_video_1", "test_channel_a", view_count=100, published_at="2026-09-01T00:00:00Z"),
        video("test_video_2", "test_channel_a", view_count=200, published_at="2026-10-01T00:00:00Z"),
        video("test_video_3", "test_channel_b", view_count=50, published_at="2026-10-05T00:00:00Z"),
    ])
    store_records("videos", [video("test_video_1", "test_channel_a", collected_at=DAY2, view_count=150,
                                   published_at="2026-09-01T00:00:00Z")])
    store_records("comments", [
        comment("test_comment_1", "test_video_1"),
        comment("test_comment_2", "test_video_1", author_channel_id=None),
        comment("test_comment_3", "test_video_3", "test_channel_b", collected_at=DAY2),
    ])


def test_create_views_and_query(stored):
    with duckdb_connection() as con:
        views = create_views(con)
        assert sorted(views) == sorted(["channels", "channels_history", "videos", "videos_history",
                                        "comments", "comments_history"])

        def one(sql):
            return con.execute(sql).fetchone()[0]

        assert one("SELECT count(*) FROM channels") == 2
        assert one("SELECT count(*) FROM videos") == 3
        assert one("SELECT count(*) FROM videos_history") == 4
        assert one("SELECT count(*) FROM comments") == 3

        per_channel = con.execute("""
            SELECT channel_id, count(*) AS videos, CAST(sum(view_count) AS BIGINT) AS views
            FROM videos GROUP BY channel_id ORDER BY channel_id
        """).fetchall()
        assert per_channel == [("test_channel_a", 2, 350), ("test_channel_b", 1, 50)]

        activity = con.execute("""
            SELECT v.video_id, count(c.comment_id) AS comments, count(c.author_channel_id) AS with_author
            FROM videos v LEFT JOIN comments c USING (video_id)
            GROUP BY v.video_id ORDER BY v.video_id
        """).fetchall()
        assert activity == [("test_video_1", 2, 1), ("test_video_2", 0, 0), ("test_video_3", 1, 1)]

        assert one("SELECT count(*) FROM comments WHERE collected_at >= TIMESTAMPTZ '2026-10-08 00:00:00+00'") == 1
        assert one("SELECT count(*) FROM videos WHERE published_at >= TIMESTAMPTZ '2026-10-01 00:00:00+00'") == 2

        growth = con.execute("""
            SELECT collected_at, view_count FROM videos_history
            WHERE video_id = 'test_video_1' ORDER BY collected_at
        """).fetchall()
        assert [v for _, v in growth] == [100, 150]
        assert growth[0][0] == datetime(2026, 10, 7, 8, tzinfo=timezone.utc)


def test_views_persist_in_database_file(stored):
    with duckdb_connection() as con:
        create_views(con)
    with duckdb_connection() as con:  # reopened later
        assert con.execute("SELECT count(*) FROM videos").fetchone()[0] == 3


def test_views_use_project_relative_paths(project_root):
    store_records("channels", [channel()])
    with duckdb_connection() as con:
        create_views(con)
        sql = con.execute("SELECT sql FROM duckdb_views() WHERE view_name = 'channels'").fetchone()[0]
    assert "data/processed/channels.parquet" in sql
    assert str(project_root) not in sql and project_root.as_posix() not in sql


def test_create_views_skips_missing_datasets(isolated_data_dir):
    store_records("channels", [channel()])
    with duckdb_connection(":memory:") as con:
        assert sorted(create_views(con)) == ["channels", "channels_history"]


# --- errors --------------------------------------------------------------------

def test_invalid_record_rejected_and_nothing_written(isolated_data_dir):
    with pytest.raises(ValidationError):
        store_records("videos", [video().model_dump(), {**video("test_video_2").model_dump(), "view_count": -1}])
    assert not latest_path("videos").exists()
    assert not snapshot_path("videos", "2026-10-07").exists()


def test_missing_required_field(isolated_data_dir):
    data = channel().model_dump()
    del data["channel_id"]
    with pytest.raises(ValidationError, match="channel_id"):
        store_records("channels", [data])


def test_invalid_timestamp(isolated_data_dir):
    with pytest.raises(ValidationError):
        store_records("channels", [{**channel().model_dump(), "collected_at": "2026-10-07 08:00"}])


def test_unknown_dataset(isolated_data_dir):
    with pytest.raises(ValueError, match="Unknown dataset"):
        store_records("playlists", [])


def test_wrong_record_type(isolated_data_dir):
    with pytest.raises(TypeError, match="expects Video"):
        store_records("videos", [channel()])


def test_incompatible_existing_file(isolated_data_dir):
    write_dataset(pd.DataFrame({"video_id": ["test_video_1"], "old_column": [1]}), latest_path("videos"))
    with pytest.raises(SchemaError, match="does not match the Video schema"):
        store_records("videos", [video()])
    with pytest.raises(SchemaError):
        read_latest("videos")


def test_corrupted_file(isolated_data_dir):
    path = latest_path("channels")
    path.parent.mkdir(parents=True)
    path.write_bytes(b"this is not parquet")
    with pytest.raises(DatasetReadError, match="Cannot read"):
        read_latest("channels")
    with pytest.raises(DatasetReadError):
        store_records("channels", [channel()])
    assert not snapshot_path("channels", "2026-10-07").exists()  # failed before writing anything


def test_read_missing_dataset(isolated_data_dir):
    with pytest.raises(FileNotFoundError):
        read_latest("comments")
    with pytest.raises(FileNotFoundError):
        read_snapshot("comments", "2026-10-07")
    assert read_history("comments").empty
