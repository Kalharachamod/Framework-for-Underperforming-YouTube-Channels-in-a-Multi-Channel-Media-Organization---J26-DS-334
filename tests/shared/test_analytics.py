"""Tests for the DuckDB analytical query layer (shared/utils/analytics.py).

All records are TEST DATA: synthetic IDs, names and text invented for testing.
They are not real YouTube channels, videos, comments or commenters.
"""

from datetime import date, datetime, timezone

import pandas as pd
import pytest

from shared.schemas import Channel, Comment, Video, to_dataframe
from shared.utils import DatasetNotFoundError, latest_path, store_records, write_dataset
from shared.utils import analytics as a
from shared.utils.analytics import InvalidQueryParameter

COLLECTED = "2026-10-07T08:00:00Z"


# --- TEST DATA ------------------------------------------------------------------------
#
# channel        subscribers  videos (published, views, likes, comment_count)
# test_ch_a      1000         v1 (09-01, 100, 10, 2)  v2 (10-01, 300, 20, 0)  v4 (10-06 00:30, 0, 0, 0)
# test_ch_b      hidden       v3 (10-05 23:30, 50, hidden, 1)
# test_ch_c      50           -
#
# comments: c1 on v1 (09-02), c2 on v1 (10-01, no author id), c3 on v3 (10-06)

def _channels():
    return [
        Channel(channel_id="test_ch_a", channel_name="Test Alpha", subscriber_count=1000,
                view_count=400, video_count=3, collected_at=COLLECTED),
        Channel(channel_id="test_ch_b", channel_name="Test Beta", subscriber_count=None,
                view_count=50, video_count=1, collected_at=COLLECTED),
        Channel(channel_id="test_ch_c", channel_name="Test Gamma", subscriber_count=50,
                view_count=0, video_count=0, collected_at=COLLECTED),
    ]


def _video(vid, cid, published, views, likes, comments):
    return Video(video_id=vid, channel_id=cid, title=f"Test {vid}", published_at=published,
                 tags=["test"], view_count=views, like_count=likes, comment_count=comments,
                 collected_at=COLLECTED)


def _videos():
    return [
        _video("test_v1", "test_ch_a", "2026-09-01T10:00:00Z", 100, 10, 2),
        _video("test_v2", "test_ch_a", "2026-10-01T10:00:00Z", 300, 20, 0),
        _video("test_v3", "test_ch_b", "2026-10-05T23:30:00Z", 50, None, 1),
        _video("test_v4", "test_ch_a", "2026-10-06T00:30:00Z", 0, 0, 0),
    ]


def _comment(com, vid, cid, published, author="test_author_1", likes=0):
    return Comment(comment_id=com, video_id=vid, channel_id=cid, author_channel_id=author,
                   comment_text="Synthetic test comment.", published_at=published,
                   like_count=likes, collected_at=COLLECTED)


def _comments():
    return [
        _comment("test_c1", "test_v1", "test_ch_a", "2026-09-02T00:00:00Z", likes=1),
        _comment("test_c2", "test_v1", "test_ch_a", "2026-10-01T12:00:00Z", author=None),
        _comment("test_c3", "test_v3", "test_ch_b", "2026-10-06T08:00:00Z", author="test_author_2"),
    ]


@pytest.fixture
def data(isolated_data_dir):
    store_records("channels", _channels())
    store_records("videos", _videos())
    store_records("comments", _comments())
    return isolated_data_dir


# --- session and basic reads ---------------------------------------------------------

def test_session_registers_dataset_views(data):
    with a.research_session() as con:
        views = {r[0] for r in con.execute("SELECT view_name FROM duckdb_views() WHERE NOT internal").fetchall()}
        assert {"channels", "videos", "comments"} <= views
        assert {"channels_history", "videos_history", "comments_history"} <= views


def test_session_reused_across_queries(data):
    with a.research_session() as con:
        assert a.count_channels(con=con) == 3
        assert len(a.get_channel_videos("test_ch_a", con=con)) == 3


def test_reads_each_dataset_with_schema_columns(data):
    assert list(a.get_channels().columns) == list(Channel.DTYPES)
    assert len(a.get_videos()) == 4 and list(a.get_videos().columns) == list(Video.DTYPES)
    assert len(a.get_comments()) == 3 and list(a.get_comments().columns) == list(Comment.DTYPES)


def test_queries_never_write(data):
    before = {p: p.read_bytes() for p in data.rglob("*.parquet")}
    a.channel_summary()
    a.videos_with_comments()
    assert {p: p.read_bytes() for p in data.rglob("*.parquet")} == before
    assert not (data / "test.duckdb").exists()  # in-memory session only


# --- channels -------------------------------------------------------------------

def test_get_channel(data):
    ch = a.get_channel("test_ch_a")
    assert len(ch) == 1 and ch.loc[0, "channel_name"] == "Test Alpha"


def test_unknown_channel_returns_empty(data):
    assert a.get_channel("test_ch_unknown").empty
    assert a.get_channel_videos("test_ch_unknown").empty
    assert a.get_channel_comments("test_ch_unknown").empty


def test_filter_channels(data):
    assert a.filter_channels(min_subscribers=100)["channel_id"].tolist() == ["test_ch_a"]
    assert a.filter_channels(max_subscribers=100)["channel_id"].tolist() == ["test_ch_c"]
    # Hidden subscriber count never matches a count filter.
    assert "test_ch_b" not in a.filter_channels(min_subscribers=0)["channel_id"].tolist()
    assert a.filter_channels(name_contains="beta")["channel_id"].tolist() == ["test_ch_b"]
    assert a.filter_channels(name_contains="test", limit=2)["channel_id"].tolist() == ["test_ch_a", "test_ch_b"]
    assert len(a.filter_channels()) == 3


def test_count_channels(data):
    assert a.count_channels() == 3


# --- videos ---------------------------------------------------------------------

def test_channel_videos_newest_first(data):
    assert a.get_channel_videos("test_ch_a")["video_id"].tolist() == ["test_v4", "test_v2", "test_v1"]
    assert a.get_channel_videos("test_ch_a", limit=1)["video_id"].tolist() == ["test_v4"]


def test_videos_by_date_range_inclusive_utc_days(data):
    got = a.get_videos(start=date(2026, 10, 1), end=date(2026, 10, 5))
    assert got["video_id"].tolist() == ["test_v2", "test_v3"]  # v3 at 23:30 on the end day included


def test_videos_by_datetime_and_iso_strings(data):
    colombo = datetime.fromisoformat("2026-10-06T05:00:00+05:30")  # = 2026-10-05 23:30 UTC
    assert a.get_videos(start=colombo)["video_id"].tolist() == ["test_v3", "test_v4"]
    assert a.get_videos(start="2026-10-06")["video_id"].tolist() == ["test_v4"]
    assert a.get_videos(end="2026-09-01T10:00:00Z")["video_id"].tolist() == ["test_v1"]


def test_videos_by_collected_at(data):
    assert len(a.get_videos(start="2026-10-07", date_field="collected_at")) == 4
    assert a.get_videos(end="2026-10-06", date_field="collected_at").empty


def test_videos_filters_combine(data):
    got = a.get_videos(channel_id="test_ch_a", min_views=100)
    assert got["video_id"].tolist() == ["test_v1", "test_v2"]


def test_recent_videos(data):
    assert a.recent_videos(limit=2)["video_id"].tolist() == ["test_v4", "test_v3"]
    assert a.recent_videos(channel_id="test_ch_b")["video_id"].tolist() == ["test_v3"]


def test_count_videos_by_channel(data):
    got = a.count_videos_by_channel()
    assert list(got.itertuples(index=False, name=None)) == [("test_ch_a", 3), ("test_ch_b", 1)]


def test_channel_video_metrics_handles_hidden_metrics(data):
    m = a.channel_video_metrics().set_index("channel_id")
    assert m.loc["test_ch_a", ["total_views", "total_likes", "total_comment_count"]].tolist() == [400, 30, 2]
    assert m.loc["test_ch_b", "total_views"] == 50
    assert pd.isna(m.loc["test_ch_b", "total_likes"])  # hidden, not zero
    assert m.loc["test_ch_b", "likes_known"] == 0
    assert m["total_views"].dtype == "int64"


# --- comments -------------------------------------------------------------------

def test_video_comments(data):
    got = a.get_video_comments("test_v1")
    assert got["comment_id"].tolist() == ["test_c1", "test_c2"]
    assert got["author_channel_id"].isna().tolist() == [False, True]
    assert a.get_video_comments("test_v2").empty
    assert a.get_video_comments("test_v_unknown").empty


def test_channel_comments_through_videos(data):
    assert a.get_channel_comments("test_ch_a")["comment_id"].tolist() == ["test_c1", "test_c2"]
    assert a.get_channel_comments("test_ch_b")["comment_id"].tolist() == ["test_c3"]
    assert a.get_channel_comments("test_ch_c").empty


def test_comments_by_date_range(data):
    assert a.get_comments(start="2026-10-01")["comment_id"].tolist() == ["test_c2", "test_c3"]
    assert a.get_comments(start="2026-10-01", video_id="test_v1")["comment_id"].tolist() == ["test_c2"]
    assert a.get_comments(start="2027-01-01").empty  # no matching records


def test_count_comments_by_video(data):
    got = a.count_comments_by_video()
    assert dict(zip(got["video_id"], got["stored_comments"])) == {
        "test_v1": 2, "test_v2": 0, "test_v3": 1, "test_v4": 0,
    }


def test_count_comments_by_channel(data):
    got = a.count_comments_by_channel()
    assert dict(zip(got["channel_id"], got["stored_comments"])) == {"test_ch_a": 2, "test_ch_b": 1}


# --- cross-dataset ---------------------------------------------------------------

def test_channels_with_videos(data):
    got = a.channels_with_videos()
    assert len(got) == 4
    assert set(got.loc[got["channel_id"] == "test_ch_a", "channel_name"]) == {"Test Alpha"}
    assert "test_ch_c" not in set(got["channel_id"])  # no videos
    assert a.channels_with_videos(channel_id="test_ch_b")["video_id"].tolist() == ["test_v3"]
    assert "video_collected_at" in got.columns and got.columns.is_unique


def test_videos_with_comments(data):
    got = a.videos_with_comments()
    assert got["comment_id"].tolist() == ["test_c1", "test_c2", "test_c3"]
    assert got.loc[2, "channel_id"] == "test_ch_b"
    assert got.columns.is_unique
    assert a.videos_with_comments(video_id="test_v1")["comment_id"].tolist() == ["test_c1", "test_c2"]


def test_channel_summary(data):
    s = a.channel_summary().set_index("channel_id")
    assert s.loc["test_ch_a", "videos"] == 3
    assert s.loc["test_ch_a", "stored_comments"] == 2
    assert s.loc["test_ch_a", "total_views"] == 400
    assert s.loc["test_ch_a", "engagement_rate"] == pytest.approx((10 + 2 + 20 + 0) / 400)
    assert pd.isna(s.loc["test_ch_b", "engagement_rate"])  # likes hidden -> not computable
    assert s.loc["test_ch_c", "videos"] == 0 and s.loc["test_ch_c", "stored_comments"] == 0
    assert pd.isna(s.loc["test_ch_c", "total_views"])


# --- results ----------------------------------------------------------------------

def test_to_records(data):
    rows = a.to_records(a.get_video_comments("test_v1"))
    assert rows[1]["author_channel_id"] is None
    assert rows[0]["published_at"] == datetime(2026, 9, 2, tzinfo=timezone.utc)
    assert a.to_records(a.get_channel("test_ch_unknown")) == []


def test_timestamps_are_utc(data):
    assert str(a.get_videos()["published_at"].dt.tz) == "UTC"


def test_run_query_with_parameters(data):
    got = a.run_query("SELECT video_id FROM videos WHERE view_count > ? ORDER BY video_id", [60])
    assert got["video_id"].tolist() == ["test_v1", "test_v2"]


def test_history_view_available(data):
    store_records("videos", [_video("test_v1", "test_ch_a", "2026-09-01T10:00:00Z", 180, 12, 3)
                             .model_copy(update={"collected_at": datetime(2026, 10, 8, tzinfo=timezone.utc)})])
    got = a.run_query("SELECT view_count FROM videos_history WHERE video_id = ? ORDER BY collected_at", ["test_v1"])
    assert got["view_count"].tolist() == [100, 180]
    assert a.get_channel_videos("test_ch_a").set_index("video_id").loc["test_v1", "view_count"] == 180


# --- safety and invalid parameters -------------------------------------------------

@pytest.mark.parametrize("bad_id", ["", "   ", "x' OR '1'='1", "a; DROP TABLE videos", None, 42, "a b"])
def test_invalid_ids_rejected(data, bad_id):
    with pytest.raises(InvalidQueryParameter):
        a.get_channel(bad_id)
    with pytest.raises(InvalidQueryParameter):
        a.get_video_comments(bad_id)


def test_text_filter_is_parameterized_not_executed(data):
    assert a.filter_channels(name_contains="'; DROP VIEW channels; --").empty
    assert a.filter_channels(name_contains="%").empty  # no LIKE wildcards
    assert a.count_channels() == 3


@pytest.mark.parametrize(
    "kwargs",
    [
        {"start": "2026-10-05", "end": "2026-10-01"},  # reversed
        {"start": "07/10/2026"},
        {"start": "not-a-date"},
        {"start": datetime(2026, 10, 1)},  # naive
        {"start": 20261001},
        {"date_field": "title"},
        {"date_field": "published_at; DROP VIEW videos"},
        {"min_views": -1},
        {"min_views": "100"},
        {"limit": 0},
        {"limit": True},
        {"limit": 10**9},
        {"limit": 2.5},
    ],
)
def test_invalid_video_query_parameters(data, kwargs):
    with pytest.raises(InvalidQueryParameter):
        a.get_videos(**kwargs)


def test_invalid_channel_filters(data):
    with pytest.raises(InvalidQueryParameter):
        a.filter_channels(min_subscribers=10, max_subscribers=5)
    with pytest.raises(InvalidQueryParameter):
        a.filter_channels(name_contains="  ")
    with pytest.raises(InvalidQueryParameter):
        a.filter_channels(min_subscribers=-5)


def test_same_day_start_and_end_allowed(data):
    assert a.get_videos(start="2026-10-01", end="2026-10-01")["video_id"].tolist() == ["test_v2"]


# --- missing and empty datasets --------------------------------------------------------

def test_missing_dataset_raises_clear_error(isolated_data_dir):
    store_records("channels", _channels())  # videos and comments never stored
    assert a.count_channels() == 3
    with pytest.raises(DatasetNotFoundError, match="'videos'"):
        a.get_channel_videos("test_ch_a")
    with pytest.raises(DatasetNotFoundError, match="'comments'"):
        a.count_comments_by_channel()


def test_no_datasets_at_all(isolated_data_dir):
    with pytest.raises(DatasetNotFoundError):
        a.count_channels()


def test_empty_datasets_return_empty_results(isolated_data_dir):
    for name, model in (("channels", Channel), ("videos", Video), ("comments", Comment)):
        write_dataset(to_dataframe([], model), latest_path(name))

    assert a.count_channels() == 0
    assert a.get_channels().empty
    assert a.get_videos(start="2026-01-01").empty
    assert a.count_videos_by_channel().empty
    assert a.count_comments_by_video().empty
    assert a.channel_summary().empty
    assert a.videos_with_comments().empty
