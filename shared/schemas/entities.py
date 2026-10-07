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

    DTYPES = {
        "channel_id": STRING,
        "channel_name": STRING,
        "subscriber_count": INT,
        "view_count": INT,
        "video_count": INT,
        "collected_at": TIMESTAMP,
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
    }


class Comment(ResearchRecord):
    comment_id: YouTubeId
    video_id: YouTubeId
    channel_id: YouTubeId  # channel that owns the video
    # Public platform ID of the commenter, when available. Never filled with a
    # placeholder, and hidden from repr() so it does not leak into logs.
    # Privacy processing (hashing) is a separate, later step.
    author_channel_id: YouTubeId | None = Field(default=None, repr=False)
    comment_text: str
    published_at: UtcDatetime
    like_count: Count | None = None
    collected_at: UtcDatetime

    DTYPES = {
        "comment_id": STRING,
        "video_id": STRING,
        "channel_id": STRING,
        "author_channel_id": STRING,
        "comment_text": STRING,
        "published_at": TIMESTAMP,
        "like_count": INT,
        "collected_at": TIMESTAMP,
    }
