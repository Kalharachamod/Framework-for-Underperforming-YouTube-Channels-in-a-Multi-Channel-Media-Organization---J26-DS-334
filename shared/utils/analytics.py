"""Reusable DuckDB analytical queries over the shared research datasets.

Queries read the *latest* tables written by ``store_records``
(``data/processed/{channels,videos,comments}.parquet``) through DuckDB views.
They are generic data access, not research methods.

Every function returns a pandas DataFrame (use ``to_records`` for a list of
dicts). Pass ``con`` from ``research_session()`` to run several queries on one
connection; without it each call opens and closes its own session.

Safety: user values are always bound as SQL parameters (``?``). The only
identifiers placed in SQL text come from fixed allow-lists.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import duckdb
import pandas as pd
from pydantic import TypeAdapter, ValidationError

from shared.schemas.base import YouTubeId
from shared.utils.datasets import create_views, latest_path
from shared.utils.duckdb_query import MEMORY, duckdb_connection
from shared.utils.parquet_io import DatasetNotFoundError

DATE_FIELDS = ("published_at", "collected_at")
MAX_LIMIT = 100_000

_id_adapter = TypeAdapter(YouTubeId)

Connection = duckdb.DuckDBPyConnection


class InvalidQueryParameter(ValueError):
    """A query parameter is missing, malformed or out of range."""


# --- session -------------------------------------------------------------------

@contextmanager
def research_session() -> Iterator[duckdb.DuckDBPyConnection]:
    """In-memory DuckDB session with views over the latest Parquet datasets.

    Views: ``channels``, ``videos``, ``comments`` (latest) and ``*_history``
    (all snapshots). Nothing is written to Parquet or to the database file.
    """
    with duckdb_connection(MEMORY) as con:
        create_views(con)
        yield con


def run_query(
    sql: str,
    params: list[Any] | dict[str, Any] | None = None,
    *,
    con: Connection | None = None,
) -> pd.DataFrame:
    """Run custom parameterized SQL against the dataset views."""
    if con is not None:
        return con.execute(sql, params).df()
    with research_session() as session:
        return session.execute(sql, params).df()


def to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Rows as plain dicts; missing values become ``None``."""
    return df.astype(object).where(df.notna(), None).to_dict("records")


# --- channels --------------------------------------------------------------------

def get_channels(*, con: Connection | None = None) -> pd.DataFrame:
    return _run("SELECT * FROM channels ORDER BY channel_id", [], ["channels"], con)


def get_channel(channel_id: str, *, con: Connection | None = None) -> pd.DataFrame:
    """One channel (empty DataFrame if the id is unknown)."""
    return _run("SELECT * FROM channels WHERE channel_id = ?", [_id(channel_id)], ["channels"], con)


def filter_channels(
    *,
    min_subscribers: int | None = None,
    max_subscribers: int | None = None,
    name_contains: str | None = None,
    limit: int | None = None,
    con: Connection | None = None,
) -> pd.DataFrame:
    """Channels matching all given filters. Hidden subscriber counts (NULL) never match a count filter."""
    where, params = [], []
    if min_subscribers is not None:
        where.append("subscriber_count >= ?")
        params.append(_count(min_subscribers, "min_subscribers"))
    if max_subscribers is not None:
        where.append("subscriber_count <= ?")
        params.append(_count(max_subscribers, "max_subscribers"))
    if min_subscribers is not None and max_subscribers is not None and min_subscribers > max_subscribers:
        raise InvalidQueryParameter("min_subscribers must not exceed max_subscribers")
    if name_contains is not None:
        if not isinstance(name_contains, str) or not name_contains.strip():
            raise InvalidQueryParameter("name_contains must be a non-empty string")
        where.append("contains(lower(channel_name), lower(?))")  # literal match, no wildcards
        params.append(name_contains.strip())
    sql = f"SELECT * FROM channels {_where(where)} ORDER BY channel_id {_limit(limit, params)}"
    return _run(sql, params, ["channels"], con)


def count_channels(*, con: Connection | None = None) -> int:
    return int(_run("SELECT count(*) AS n FROM channels", [], ["channels"], con).iloc[0, 0])


# --- videos ----------------------------------------------------------------------

def get_channel_videos(channel_id: str, *, limit: int | None = None, con: Connection | None = None) -> pd.DataFrame:
    """Videos of one channel, newest published first."""
    params = [_id(channel_id)]
    sql = f"""
        SELECT * FROM videos WHERE channel_id = ?
        ORDER BY published_at DESC, video_id {_limit(limit, params)}
    """
    return _run(sql, params, ["videos"], con)


def get_videos(
    *,
    start: date | datetime | str | None = None,
    end: date | datetime | str | None = None,
    date_field: str = "published_at",
    channel_id: str | None = None,
    min_views: int | None = None,
    limit: int | None = None,
    con: Connection | None = None,
) -> pd.DataFrame:
    """Videos filtered by date range (inclusive), channel and minimum views."""
    where, params = _date_range(start, end, date_field)
    if channel_id is not None:
        where.append("channel_id = ?")
        params.append(_id(channel_id))
    if min_views is not None:
        where.append("view_count >= ?")
        params.append(_count(min_views, "min_views"))
    sql = f"SELECT * FROM videos {_where(where)} ORDER BY {date_field}, video_id {_limit(limit, params)}"
    return _run(sql, params, ["videos"], con)


def recent_videos(*, limit: int = 10, channel_id: str | None = None, con: Connection | None = None) -> pd.DataFrame:
    """Most recently published videos (optionally for one channel)."""
    where, params = [], []
    if channel_id is not None:
        where.append("channel_id = ?")
        params.append(_id(channel_id))
    sql = f"SELECT * FROM videos {_where(where)} ORDER BY published_at DESC, video_id {_limit(limit, params)}"
    return _run(sql, params, ["videos"], con)


def count_videos_by_channel(*, con: Connection | None = None) -> pd.DataFrame:
    """Stored videos per channel (channels with no stored videos are not listed)."""
    sql = "SELECT channel_id, count(*) AS video_count FROM videos GROUP BY channel_id ORDER BY channel_id"
    return _run(sql, [], ["videos"], con)


def channel_video_metrics(*, con: Connection | None = None) -> pd.DataFrame:
    """Per channel: stored videos and summed views / likes / comment counts.

    Sums skip unavailable (NULL) metrics; ``*_known`` columns say how many
    videos contributed, so hidden likes are not mistaken for zero likes.
    """
    sql = """
        SELECT channel_id,
               count(*)                          AS videos,
               CAST(sum(view_count) AS BIGINT)    AS total_views,
               CAST(sum(like_count) AS BIGINT)    AS total_likes,
               CAST(sum(comment_count) AS BIGINT) AS total_comment_count,
               count(view_count)                  AS views_known,
               count(like_count)                  AS likes_known,
               count(comment_count)               AS comment_count_known
        FROM videos GROUP BY channel_id ORDER BY channel_id
    """
    return _run(sql, [], ["videos"], con)


# --- comments --------------------------------------------------------------------

def get_video_comments(video_id: str, *, limit: int | None = None, con: Connection | None = None) -> pd.DataFrame:
    """Stored comments on one video, oldest first."""
    params = [_id(video_id)]
    sql = f"""
        SELECT * FROM comments WHERE video_id = ?
        ORDER BY published_at, comment_id {_limit(limit, params)}
    """
    return _run(sql, params, ["comments"], con)


def get_channel_comments(channel_id: str, *, limit: int | None = None, con: Connection | None = None) -> pd.DataFrame:
    """Comments on a channel's videos, found through the video relationship."""
    params = [_id(channel_id)]
    sql = f"""
        SELECT c.* FROM comments c
        JOIN videos v ON v.video_id = c.video_id
        WHERE v.channel_id = ?
        ORDER BY c.published_at, c.comment_id {_limit(limit, params)}
    """
    return _run(sql, params, ["comments", "videos"], con)


def get_comments(
    *,
    start: date | datetime | str | None = None,
    end: date | datetime | str | None = None,
    date_field: str = "published_at",
    video_id: str | None = None,
    limit: int | None = None,
    con: Connection | None = None,
) -> pd.DataFrame:
    """Comments filtered by date range (inclusive) and video."""
    where, params = _date_range(start, end, date_field)
    if video_id is not None:
        where.append("video_id = ?")
        params.append(_id(video_id))
    sql = f"SELECT * FROM comments {_where(where)} ORDER BY {date_field}, comment_id {_limit(limit, params)}"
    return _run(sql, params, ["comments"], con)


def count_comments_by_video(*, con: Connection | None = None) -> pd.DataFrame:
    """Stored comments per video, including videos with none (0)."""
    sql = """
        SELECT v.video_id, v.channel_id, count(c.comment_id) AS stored_comments
        FROM videos v LEFT JOIN comments c ON c.video_id = v.video_id
        GROUP BY v.video_id, v.channel_id ORDER BY v.video_id
    """
    return _run(sql, [], ["videos", "comments"], con)


def count_comments_by_channel(*, con: Connection | None = None) -> pd.DataFrame:
    """Stored comments per channel, through the video relationship."""
    sql = """
        SELECT v.channel_id, count(c.comment_id) AS stored_comments
        FROM videos v LEFT JOIN comments c ON c.video_id = v.video_id
        GROUP BY v.channel_id ORDER BY v.channel_id
    """
    return _run(sql, [], ["videos", "comments"], con)


# --- cross-dataset ---------------------------------------------------------------

def channels_with_videos(*, channel_id: str | None = None, con: Connection | None = None) -> pd.DataFrame:
    """One row per video, with its channel's name and subscriber count."""
    where, params = [], []
    if channel_id is not None:
        where.append("ch.channel_id = ?")
        params.append(_id(channel_id))
    sql = f"""
        SELECT ch.channel_id, ch.channel_name, ch.subscriber_count,
               v.video_id, v.title, v.published_at, v.view_count, v.like_count, v.comment_count,
               v.collected_at AS video_collected_at
        FROM channels ch JOIN videos v ON v.channel_id = ch.channel_id
        {_where(where)}
        ORDER BY ch.channel_id, v.published_at, v.video_id
    """
    return _run(sql, params, ["channels", "videos"], con)


def videos_with_comments(*, video_id: str | None = None, con: Connection | None = None) -> pd.DataFrame:
    """One row per stored comment, with its video's channel, title and publish time."""
    where, params = [], []
    if video_id is not None:
        where.append("v.video_id = ?")
        params.append(_id(video_id))
    sql = f"""
        SELECT v.channel_id, v.video_id, v.title, v.published_at AS video_published_at,
               c.comment_id, c.author_channel_id, c.comment_text,
               c.published_at AS comment_published_at, c.like_count AS comment_like_count
        FROM videos v JOIN comments c ON c.video_id = v.video_id
        {_where(where)}
        ORDER BY v.video_id, c.published_at, c.comment_id
    """
    return _run(sql, params, ["videos", "comments"], con)


def channel_summary(*, con: Connection | None = None) -> pd.DataFrame:
    """Per channel: stored videos, comments and basic engagement figures.

    ``engagement_rate`` = (likes + comment_count) / views over videos where all
    three are known; NULL when no such video exists. A descriptive statistic,
    not a research score.
    """
    sql = """
        WITH v AS (
            SELECT channel_id,
                   count(*)                          AS videos,
                   CAST(sum(view_count) AS BIGINT)    AS total_views,
                   CAST(sum(like_count) AS BIGINT)    AS total_likes,
                   CAST(sum(comment_count) AS BIGINT) AS total_comment_count,
                   avg(view_count)                    AS avg_views_per_video,
                   sum(like_count + comment_count) FILTER (WHERE view_count > 0)
                     / sum(view_count) FILTER (WHERE view_count > 0
                                               AND like_count IS NOT NULL
                                               AND comment_count IS NOT NULL)
                                                      AS engagement_rate
            FROM videos GROUP BY channel_id
        ),
        c AS (
            SELECT v.channel_id, count(*) AS stored_comments
            FROM comments c JOIN videos v ON v.video_id = c.video_id
            GROUP BY v.channel_id
        )
        SELECT ch.channel_id, ch.channel_name, ch.subscriber_count,
               coalesce(v.videos, 0)          AS videos,
               v.total_views, v.total_likes, v.total_comment_count,
               v.avg_views_per_video,
               coalesce(c.stored_comments, 0) AS stored_comments,
               v.engagement_rate
        FROM channels ch
        LEFT JOIN v ON v.channel_id = ch.channel_id
        LEFT JOIN c ON c.channel_id = ch.channel_id
        ORDER BY ch.channel_id
    """
    return _run(sql, [], ["channels", "videos", "comments"], con)


# --- helpers ---------------------------------------------------------------------

def _run(sql: str, params: list[Any], needs: list[str], con: Connection | None) -> pd.DataFrame:
    if con is None:
        with research_session() as session:
            return _run(sql, params, needs, session)
    _require(con, needs)
    return con.execute(sql, params).df()


def _require(con: duckdb.DuckDBPyConnection, datasets: list[str]) -> None:
    views = {row[0] for row in con.execute("SELECT view_name FROM duckdb_views() WHERE NOT internal").fetchall()}
    missing = [name for name in datasets if name not in views]
    if missing:
        details = ", ".join(f"'{name}' (expected {latest_path(name)})" for name in missing)
        raise DatasetNotFoundError(
            f"Dataset {details} has not been stored yet; store records with store_records() first"
        )


def _id(value: Any) -> str:
    try:
        return _id_adapter.validate_python(value)
    except ValidationError:
        raise InvalidQueryParameter(f"invalid YouTube id: {value!r}") from None


def _count(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidQueryParameter(f"{name} must be a non-negative integer, got {value!r}")
    return value


def _limit(limit: Any, params: list[Any]) -> str:
    """Return a LIMIT clause and bind its value (None = no limit)."""
    if limit is None:
        return ""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise InvalidQueryParameter(f"limit must be an integer from 1 to {MAX_LIMIT}, got {limit!r}")
    params.append(limit)
    return "LIMIT ?"


def _where(conditions: list[str]) -> str:
    return f"WHERE {' AND '.join(conditions)}" if conditions else ""


def _date_range(start: Any, end: Any, date_field: str) -> tuple[list[str], list[Any]]:
    """Inclusive range on an allow-listed timestamp column.

    A ``date`` covers that whole UTC day; datetimes must include a time zone.
    """
    if date_field not in DATE_FIELDS:
        raise InvalidQueryParameter(f"date_field must be one of {DATE_FIELDS}, got {date_field!r}")
    where, params = [], []
    lo = _bound(start, "start", end_of_day=False)
    hi = _bound(end, "end", end_of_day=True)
    if lo is not None and hi is not None and lo >= hi:
        raise InvalidQueryParameter("start must be before end")
    if lo is not None:
        where.append(f"{date_field} >= ?")
        params.append(lo)
    if hi is not None:
        where.append(f"{date_field} < ?")
        params.append(hi)
    return where, params


def _bound(value: Any, name: str, *, end_of_day: bool) -> datetime | None:
    """Convert a date bound to a UTC datetime; ``end`` becomes an exclusive upper bound."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            text = value.strip().replace("Z", "+00:00")
            value = datetime.fromisoformat(text) if "T" in text or " " in text else date.fromisoformat(text)
        except ValueError:
            raise InvalidQueryParameter(f"{name} is not an ISO date or datetime: {value!r}") from None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise InvalidQueryParameter(f"{name} datetime must include a time zone")
        value = value.astimezone(timezone.utc)
        return value + timedelta(microseconds=1) if end_of_day else value
    if isinstance(value, date):
        start_of_day = datetime.combine(value, time.min, tzinfo=timezone.utc)
        return start_of_day + timedelta(days=1) if end_of_day else start_of_day
    raise InvalidQueryParameter(f"{name} must be a date, datetime or ISO string, got {type(value).__name__}")


__all__ = [
    "DATE_FIELDS",
    "InvalidQueryParameter",
    "channel_summary",
    "channel_video_metrics",
    "channels_with_videos",
    "count_channels",
    "count_comments_by_channel",
    "count_comments_by_video",
    "count_videos_by_channel",
    "filter_channels",
    "get_channel",
    "get_channel_comments",
    "get_channel_videos",
    "get_channels",
    "get_comments",
    "get_video_comments",
    "get_videos",
    "recent_videos",
    "research_session",
    "run_query",
    "to_records",
]
