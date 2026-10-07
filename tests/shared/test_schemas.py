"""Tests for the shared research schemas.

All records here are TEST DATA: synthetic IDs and text invented for testing.
They are not real YouTube channels, videos, comments or commenters.
"""

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from pydantic import ValidationError

from shared.schemas import SCHEMA_VERSION, Channel, Comment, Video, to_dataframe
from shared.utils import query_parquet, read_dataset, snapshot_dir, write_dataset

COLLECTED = "2026-10-07T12:00:00Z"


# --- TEST DATA builders --------------------------------------------------------

def channel(**overrides) -> dict:
    data = {
        "channel_id": "test_channel_a",
        "channel_name": "Test Channel A",
        "subscriber_count": 1200,
        "view_count": 50000,
        "video_count": 30,
        "collected_at": COLLECTED,
    }
    return {**data, **overrides}


def video(**overrides) -> dict:
    data = {
        "video_id": "test_video_1",
        "channel_id": "test_channel_a",
        "title": "Test video one",
        "description": "Synthetic description for tests.",
        "published_at": "2026-10-01T09:00:00Z",
        "tags": ["test", "sample"],
        "view_count": 500,
        "like_count": 40,
        "comment_count": 3,
        "collected_at": COLLECTED,
    }
    return {**data, **overrides}


def comment(**overrides) -> dict:
    data = {
        "comment_id": "test_comment_1",
        "video_id": "test_video_1",
        "channel_id": "test_channel_a",
        "author_channel_id": "test_author_1",
        "comment_text": "Synthetic test comment.",
        "published_at": "2026-10-02T10:00:00Z",
        "like_count": 2,
        "collected_at": COLLECTED,
    }
    return {**data, **overrides}


# --- Channel -----------------------------------------------------------------

def test_valid_channel():
    c = Channel(**channel())
    assert c.channel_id == "test_channel_a"
    assert c.subscriber_count == 1200
    assert c.collected_at == datetime(2026, 10, 7, 12, tzinfo=timezone.utc)


def test_channel_metrics_are_optional():
    c = Channel(channel_id="test_channel_a", channel_name="A", collected_at=COLLECTED)
    assert (c.subscriber_count, c.view_count, c.video_count) == (None, None, None)


def test_channel_accepts_zero_metrics():
    c = Channel(**channel(subscriber_count=0, view_count=0, video_count=0))
    assert c.subscriber_count == 0


def test_channel_accepts_numeric_strings_from_api():
    # The YouTube API returns statistics as strings, e.g. "1200".
    assert Channel(**channel(subscriber_count="1200")).subscriber_count == 1200


@pytest.mark.parametrize(
    "overrides",
    [
        {"channel_id": ""},
        {"channel_id": "   "},
        {"channel_id": "has space"},
        {"channel_id": "bad/id"},
        {"channel_id": 12345},
        {"channel_id": None},
        {"channel_name": ""},
        {"subscriber_count": -1},
        {"view_count": "abc"},
        {"video_count": 1.5},
        {"video_count": True},
        {"collected_at": "not a date"},
        {"collected_at": "2026-10-07T12:00:00"},  # naive: no time zone
        {"unexpected_field": 1},
    ],
)
def test_invalid_channel(overrides):
    with pytest.raises(ValidationError):
        Channel(**channel(**overrides))


def test_channel_missing_required_fields():
    with pytest.raises(ValidationError) as err:
        Channel(collected_at=COLLECTED)
    missing = {e["loc"][0] for e in err.value.errors()}
    assert missing == {"channel_id", "channel_name"}


def test_ids_are_trimmed():
    assert Channel(**channel(channel_id="  test_channel_a  ")).channel_id == "test_channel_a"


def test_records_are_immutable():
    c = Channel(**channel())
    with pytest.raises(ValidationError):
        c.subscriber_count = 5


# --- Video -------------------------------------------------------------------

def test_valid_video():
    v = Video(**video())
    assert v.tags == ["test", "sample"]
    assert v.published_at.tzinfo == timezone.utc


def test_video_optional_fields():
    v = Video(
        video_id="test_video_2",
        channel_id="test_channel_a",
        title="",
        published_at="2026-10-01T09:00:00Z",
        collected_at=COLLECTED,
    )
    assert v.description is None
    assert v.tags == []
    assert (v.view_count, v.like_count, v.comment_count) == (None, None, None)


def test_video_zero_likes_and_comments_are_valid():
    v = Video(**video(like_count=0, comment_count=0))
    assert (v.like_count, v.comment_count) == (0, 0)


def test_video_title_kept_as_given():
    title = "  Test <b>title</b> with 'quotes' — and unicode සිංහල  "
    assert Video(**video(title=title)).title == title


@pytest.mark.parametrize(
    "overrides",
    [
        {"video_id": ""},
        {"channel_id": None},
        {"title": None},
        {"like_count": -5},
        {"comment_count": "many"},
        {"published_at": "2026-13-40T00:00:00Z"},
        {"published_at": datetime(2026, 10, 1, 9, 0)},  # naive
        {"tags": "music,dance"},  # a string, not a list
        {"tags": ["ok", 3]},
        {"tags": [None]},
    ],
)
def test_invalid_video(overrides):
    with pytest.raises(ValidationError):
        Video(**video(**overrides))


def test_tags_are_normalised():
    assert Video(**video(tags=None)).tags == []
    assert Video(**video(tags=("a", "b"))).tags == ["a", "b"]
    assert Video(**video(tags=[" spaced ", "", "  "])).tags == ["spaced"]


# --- Comment -----------------------------------------------------------------

def test_valid_comment():
    c = Comment(**comment())
    assert c.author_channel_id == "test_author_1"
    assert c.like_count == 2


def test_comment_without_author_channel_id():
    data = comment()
    del data["author_channel_id"]
    c = Comment(**data)
    assert c.author_channel_id is None  # never replaced with placeholder data


def test_comment_author_id_explicit_none():
    assert Comment(**comment(author_channel_id=None)).author_channel_id is None


def test_comment_author_id_hidden_from_repr():
    c = Comment(**comment())
    assert "test_author_1" not in repr(c)
    assert "test_author_1" not in str(c)


def test_comment_author_id_not_hashed_by_schema():
    # Privacy processing is a separate step; the schema stores what it is given.
    assert Comment(**comment()).author_channel_id == "test_author_1"


def test_reply_comment_id_with_dot_is_valid():
    assert Comment(**comment(comment_id="test_parent.test_reply")).comment_id == "test_parent.test_reply"


@pytest.mark.parametrize(
    "overrides",
    [
        {"comment_id": ""},
        {"video_id": None},
        {"channel_id": "bad id"},
        {"author_channel_id": "bad id"},
        {"comment_text": None},
        {"like_count": -1},
        {"published_at": "yesterday"},
    ],
)
def test_invalid_comment(overrides):
    with pytest.raises(ValidationError):
        Comment(**comment(**overrides))


# --- Timestamps ----------------------------------------------------------------

def test_timestamps_converted_to_utc():
    colombo = timezone(timedelta(hours=5, minutes=30))
    v = Video(**video(published_at=datetime(2026, 10, 1, 14, 30, tzinfo=colombo)))
    assert v.published_at == datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
    assert v.published_at.utcoffset() == timedelta(0)


def test_iso_string_with_offset():
    c = Channel(**channel(collected_at="2026-10-07T17:30:00+05:30"))
    assert c.collected_at == datetime(2026, 10, 7, 12, tzinfo=timezone.utc)


# --- Serialization ---------------------------------------------------------------

def test_to_record_keeps_python_types():
    rec = Video(**video()).to_record()
    assert isinstance(rec["published_at"], datetime)
    assert rec["tags"] == ["test", "sample"]
    assert list(rec) == list(Video.DTYPES)


def test_to_json_dict_is_json_safe():
    data = Video(**video()).to_json_dict()
    assert data["published_at"] == "2026-10-01T09:00:00Z"
    assert data["tags"] == ["test", "sample"]


def test_dtypes_cover_every_field():
    for model in (Channel, Video, Comment):
        assert list(model.DTYPES) == list(model.model_fields), model.__name__


def test_to_dataframe_types():
    df = to_dataframe([Video(**video()), Video(**video(video_id="test_video_2", like_count=None, tags=[]))], Video)
    assert list(df.columns) == list(Video.DTYPES)
    assert df["view_count"].dtype == "Int64"
    assert str(df["published_at"].dtype) == "datetime64[us, UTC]"
    assert df["like_count"].isna().tolist() == [False, True]
    assert list(df.loc[1, "tags"]) == []


def test_to_dataframe_empty_list_keeps_columns():
    df = to_dataframe([], Comment)
    assert df.empty
    assert list(df.columns) == list(Comment.DTYPES)


def test_to_dataframe_rejects_wrong_model():
    with pytest.raises(TypeError):
        to_dataframe([Channel(**channel())], Video)


def test_schema_version_defined():
    assert SCHEMA_VERSION == "1.0"


# --- Parquet and DuckDB integration (STEP 02 layer) -------------------------------

def test_schema_to_parquet_round_trip(isolated_data_dir):
    videos = [
        Video(**video()),
        Video(**video(video_id="test_video_2", description=None, tags=[], like_count=None)),
    ]
    target = write_dataset(to_dataframe(videos, Video), snapshot_dir("2026-10-07") / "videos.parquet")
    back = read_dataset(target)

    assert list(back.columns) == list(Video.DTYPES)
    assert back["like_count"].isna().tolist() == [False, True]
    assert back["description"].isna().tolist() == [False, True]
    assert list(back.loc[0, "tags"]) == ["test", "sample"]
    assert list(back.loc[1, "tags"]) == []
    assert str(back["published_at"].dt.tz) == "UTC"
    # Rows read back from Parquet validate against the schema again.
    rebuilt = Video(**back.iloc[0].to_dict() | {"tags": list(back.loc[0, "tags"])})
    assert rebuilt == videos[0]


def test_parquet_schema_is_stable_when_values_are_missing(isolated_data_dir):
    # All optional values missing must still give the same column types.
    full = to_dataframe([Comment(**comment())], Comment)
    sparse = to_dataframe([Comment(**comment(author_channel_id=None, like_count=None))], Comment)
    a = write_dataset(full, isolated_data_dir / "a.parquet")
    b = write_dataset(sparse, isolated_data_dir / "b.parquet")

    describe = "SELECT column_name, column_type FROM (DESCRIBE SELECT * FROM dataset)"
    assert query_parquet(a, describe).equals(query_parquet(b, describe))


def test_duckdb_queries_schema_data(isolated_data_dir):
    snap = snapshot_dir("2026-10-07")
    write_dataset(
        to_dataframe(
            [Channel(**channel()), Channel(**channel(channel_id="test_channel_b", channel_name="B", subscriber_count=None))],
            Channel,
        ),
        snap / "channels.parquet",
    )
    write_dataset(
        to_dataframe(
            [
                Comment(**comment()),
                Comment(**comment(comment_id="test_comment_2", author_channel_id=None)),
                Comment(**comment(comment_id="test_comment_3", channel_id="test_channel_b")),
            ],
            Comment,
        ),
        snap / "comments.parquet",
    )

    per_channel = query_parquet(
        snap / "comments.parquet",
        """
        SELECT channel_id,
               count(*) AS comments,
               count(author_channel_id) AS with_author
        FROM dataset GROUP BY channel_id ORDER BY channel_id
        """,
    )
    assert per_channel["comments"].tolist() == [2, 1]
    assert per_channel["with_author"].tolist() == [1, 1]

    tags = query_parquet(
        write_dataset(to_dataframe([Video(**video())], Video), snap / "videos.parquet"),
        "SELECT unnest(tags) AS tag FROM dataset ORDER BY tag",
    )
    assert tags["tag"].tolist() == ["sample", "test"]
