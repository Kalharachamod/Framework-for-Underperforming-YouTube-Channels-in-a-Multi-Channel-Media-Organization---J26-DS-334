-- 0005_component3_live.sql
-- Component 3 live results: the nightly job (research/component_3/live.py) recomputes the Audience
-- Bridge Score on a rolling window of the newest collected data and publishes aggregate results here,
-- so the dashboard can show them without the analyst's computer.
--
-- Aggregates only: channel ids and names, counts and scores. Never commenter identifiers or comment text.
-- These are live monitoring results; the frozen thesis results stay in the immutable Parquet snapshots.
-- Apply with:  python -m shared.database.migrate

CREATE TABLE research.c3_live_runs (
    run_id              text        PRIMARY KEY CHECK (run_id ~ '^live-[0-9]{8}T[0-9]{6}Z$'),
    started_at          timestamptz NOT NULL,
    finished_at         timestamptz,
    status              text        NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    window_start        timestamptz NOT NULL,
    window_end          timestamptz NOT NULL,
    snapshot_id         text,
    experiment_id       text,
    channels            integer     CHECK (channels >= 0),
    videos              integer     CHECK (videos >= 0),
    comments            integer     CHECK (comments >= 0),
    unique_commenters   integer     CHECK (unique_commenters >= 0),
    quota_units         integer     CHECK (quota_units >= 0),
    error               text,
    details             jsonb       NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX c3_live_runs_finished_idx ON research.c3_live_runs (finished_at DESC);

CREATE TABLE research.c3_live_bridge_scores (
    run_id                  text        NOT NULL REFERENCES research.c3_live_runs (run_id) ON DELETE CASCADE,
    source_channel_id       text        NOT NULL,
    destination_channel_id  text        NOT NULL CHECK (destination_channel_id <> source_channel_id),
    source_channel_name     text,
    destination_channel_name text,
    audience_bridge_score   double precision CHECK (audience_bridge_score >= 0 AND audience_bridge_score <= 1),
    base_score              double precision,
    diffusion_component     double precision,
    embedding_component     double precision,
    topic_component         double precision,
    confidence              double precision CHECK (confidence >= 0 AND confidence <= 1),
    shared_commenters       integer     CHECK (shared_commenters >= 0),
    rank                    integer     CHECK (rank >= 1),
    score_status            text        NOT NULL,
    PRIMARY KEY (run_id, source_channel_id, destination_channel_id)
);
CREATE INDEX c3_live_bridge_pair_idx ON research.c3_live_bridge_scores (source_channel_id, destination_channel_id);

CREATE TABLE research.c3_live_channels (
    run_id              text        NOT NULL REFERENCES research.c3_live_runs (run_id) ON DELETE CASCADE,
    channel_id          text        NOT NULL,
    channel_name        text,
    videos              integer     CHECK (videos >= 0),
    comments            integer     CHECK (comments >= 0),
    unique_commenters   integer     CHECK (unique_commenters >= 0),
    PRIMARY KEY (run_id, channel_id)
);

-- same access rule as the research tables: server-side connection only
ALTER TABLE research.c3_live_runs          ENABLE ROW LEVEL SECURITY;
ALTER TABLE research.c3_live_bridge_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE research.c3_live_channels      ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        EXECUTE 'REVOKE ALL ON research.c3_live_runs, research.c3_live_bridge_scores, research.c3_live_channels FROM anon, authenticated';
    END IF;
END
$$;
