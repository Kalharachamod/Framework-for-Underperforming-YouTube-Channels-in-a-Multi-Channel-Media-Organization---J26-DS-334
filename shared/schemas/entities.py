"""Shared research schemas for the three core YouTube entities.

These describe *data*, not research methods. Collectors (later step) parse API
responses into these models; ``to_dataframe`` turns them into Parquet-ready tables.
Optional fields are ``None`` when the API does not return them.
"""

from __future__ import annotations

from pydantic import Field

from shared.schemas.base import (
    INT,
    STRING,
    STRING_LIST,
    TIMESTAMP,
    Count,
    ResearchRecord,
    Tags,
    UtcDatetime,
    YouTubeId,
)


class Channel(ResearchRecord):
    channel_id: YouTubeId
    channel_name: str = Field(min_length=1)
    subscriber_count: Count | None = None  # None when hidden or unavailable
    view_count: Count | None = None
    video_count: Count | None = None
    collected_at: UtcDatetime
    # Added in schema 1.1 (optional, so 1.0 records stay valid).
    description: str | None = None
    published_at: UtcDatetime | None = None  # when the channel was created on YouTube

    DTYPES = {
        "channel_id": STRING,
        "channel_name": STRING,
        "subscriber_count": INT,
        "view_count": INT,
        "video_count": INT,
        "collected_at": TIMESTAMP,
        "description": STRING,
        "published_at": TIMESTAMP,
    }


class Video(ResearchRecord):
    video_id: YouTubeId
    channel_id: YouTubeId
    title: str  # may be empty; stored as given
    description: str | None = None
    published_at: UtcDatetime
    tags: Tags = Field(default_factory=list)  # [] when the video has no tags
    view_count: Count | None = None
    like_count: Count | None = None  # None when likes are hidden
    comment_count: Count | None = None  # None when comments are disabled
    collected_at: UtcDatetime
    # Added in schema 1.2 (optional): length in seconds; 0 for live / upcoming streams.
    duration_seconds: Count | None = None

    DTYPES = {
        "video_id": STRING,
        "channel_id": STRING,
        "title": STRING,
        "description": STRING,
        "published_at": TIMESTAMP,
        "tags": STRING_LIST,
        "view_count": INT,
        "like_count": INT,
        "comment_count": INT,
        "collected_at": TIMESTAMP,
        "duration_seconds": INT,
    }


class Comment(ResearchRecord):
    comment_id: YouTubeId
    video_id: YouTubeId
    channel_id: YouTubeId  # channel that owns the video
    # Commenter id, when available. Never filled with a placeholder and hidden from
    # repr(). Stored only as a pseudonym (shared.utils.privacy, applied on storage).
    author_channel_id: YouTubeId | None = Field(default=None, repr=False)
    comment_text: str
    published_at: UtcDatetime
    like_count: Count | None = None
    collected_at: UtcDatetime
    # Added in schema 1.3 (optional). None for top-level comments; replies point to their thread.
    parent_comment_id: YouTubeId | None = None
    edited_at: UtcDatetime | None = None  # YouTube's last-edit time (equals published_at if never edited)

    DTYPES = {
        "comment_id": STRING,
        "video_id": STRING,
        "channel_id": STRING,
        "author_channel_id": STRING,
        "comment_text": STRING,
        "published_at": TIMESTAMP,
        "like_count": INT,
        "collected_at": TIMESTAMP,
        "parent_comment_id": STRING,
        "edited_at": TIMESTAMP,
    }
