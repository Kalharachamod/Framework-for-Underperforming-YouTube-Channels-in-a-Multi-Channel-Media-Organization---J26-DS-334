-- 0001_research_schema.sql
-- Shared research database (Supabase PostgreSQL).
-- Mirrors the STEP 03 schemas in shared/schemas/entities.py (the source of truth).
-- Apply with:  python -m shared.database.migrate
--
-- Current-state tables hold the latest observation per id; *_stats_history keep
-- every observed metric value. Immutable research snapshots are Parquet files
-- (see docs/architecture/supabase.md), not database tables.

CREATE SCHEMA IF NOT EXISTS research;

-- ---------------------------------------------------------------- channels
CREATE TABLE research.channels (
    channel_id          text        PRIMARY KEY CHECK (channel_id ~ '^[A-Za-z0-9_.-]{1,128}$'),
    channel_name        text        NOT NULL CHECK (length(channel_name) > 0),
    subscriber_count    bigint      CHECK (subscriber_count >= 0),   -- NULL when hidden
    view_count          bigint      CHECK (view_count >= 0),
    video_count         bigint      CHECK (video_count >= 0),
    collected_at        timestamptz NOT NULL,                        -- when we observed it (latest)
    first_collected_at  timestamptz NOT NULL,                        -- first time we observed it
    updated_at          timestamptz NOT NULL DEFAULT now(),          -- last write to this row
    CHECK (first_collected_at <= collected_at)
);

-- ---------------------------------------------------------------- videos
CREATE TABLE research.videos (
    video_id            text        PRIMARY KEY CHECK (video_id ~ '^[A-Za-z0-9_.-]{1,128}$'),
    channel_id          text        NOT NULL REFERENCES research.channels (channel_id) ON DELETE RESTRICT,
    title               text        NOT NULL,
    description         text,
    published_at        timestamptz NOT NULL,                        -- when YouTube published it
    tags                text[]      NOT NULL DEFAULT '{}',
    view_count          bigint      CHECK (view_count >= 0),
    like_count          bigint      CHECK (like_count >= 0),         -- NULL when hidden
    comment_count       bigint      CHECK (comment_count >= 0),      -- NULL when disabled
    collected_at        timestamptz NOT NULL,
    first_collected_at  timestamptz NOT NULL,
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (first_collected_at <= collected_at)
);
-- A channel's videos, newest first.
CREATE INDEX videos_channel_published_idx ON research.videos (channel_id, published_at DESC);
-- Date-range queries across all videos.
CREATE INDEX videos_published_idx ON research.videos (published_at);

-- ---------------------------------------------------------------- comments
CREATE TABLE research.comments (
    comment_id          text        PRIMARY KEY CHECK (comment_id ~ '^[A-Za-z0-9_.-]{1,128}$'),
    video_id            text        NOT NULL REFERENCES research.videos (video_id) ON DELETE RESTRICT,
    channel_id          text        NOT NULL REFERENCES research.channels (channel_id) ON DELETE RESTRICT,
    -- Pseudonymized commenter id only (shared/utils/privacy.py); raw YouTube ids are rejected.
    author_channel_id   text        CHECK (author_channel_id IS NULL OR author_channel_id ~ '^anon_[0-9a-f]{64}$'),
    comment_text        text        NOT NULL,
    published_at        timestamptz NOT NULL,
    like_count          bigint      CHECK (like_count >= 0),
    collected_at        timestamptz NOT NULL,
    first_collected_at  timestamptz NOT NULL,
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (first_collected_at <= collected_at)
);
-- Comments of a video in time order.
CREATE INDEX comments_video_published_idx ON research.comments (video_id, published_at);
-- Comments on a channel (Component 3: commenter-channel edges).
CREATE INDEX comments_channel_idx ON research.comments (channel_id);
-- One commenter across channels (Component 3: audience bridges); most rows have an author.
CREATE INDEX comments_author_idx ON research.comments (author_channel_id) WHERE author_channel_id IS NOT NULL;
-- Date-range queries across all comments.
CREATE INDEX comments_published_idx ON research.comments (published_at);

-- ---------------------------------------------------------------- metric history
-- Every observed metric value, so updating the current tables never loses history.
CREATE TABLE research.channel_stats_history (
    channel_id          text        NOT NULL REFERENCES research.channels (channel_id) ON DELETE CASCADE,
    collected_at        timestamptz NOT NULL,
    subscriber_count    bigint      CHECK (subscriber_count >= 0),
    view_count          bigint      CHECK (view_count >= 0),
    video_count         bigint      CHECK (video_count >= 0),
    PRIMARY KEY (channel_id, collected_at)
);

CREATE TABLE research.video_stats_history (
    video_id            text        NOT NULL REFERENCES research.videos (video_id) ON DELETE CASCADE,
    collected_at        timestamptz NOT NULL,
    view_count          bigint      CHECK (view_count >= 0),
    like_count          bigint      CHECK (like_count >= 0),
    comment_count       bigint      CHECK (comment_count >= 0),
    PRIMARY KEY (video_id, collected_at)
);

-- ---------------------------------------------------------------- access control
-- Research data is only reachable through the server-side database connection
-- (SUPABASE_DB_URL). Row-level security with no policies denies the public
-- Supabase API roles; the 'research' schema is also not exposed by the REST API.
ALTER TABLE research.channels              ENABLE ROW LEVEL SECURITY;
ALTER TABLE research.videos                ENABLE ROW LEVEL SECURITY;
ALTER TABLE research.comments              ENABLE ROW LEVEL SECURITY;
ALTER TABLE research.channel_stats_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE research.video_stats_history   ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    -- Supabase-only roles; skipped on plain PostgreSQL (e.g. local tests).
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        EXECUTE 'REVOKE ALL ON SCHEMA research FROM anon, authenticated';
        EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA research FROM anon, authenticated';
    END IF;
END
$$;
