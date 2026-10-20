-- REVIEW ONLY. Never run automatically. Requires 002a roles and 002a1 owner
-- membership first, run by an authorized deployment actor with database CREATE
-- and SET ROLE c1_owner capabilities. c1_owner does not need database CREATE.
-- Requires PostgreSQL 15+ (view security_invoker option). No credentials here.
BEGIN;
-- Deliberately no IF NOT EXISTS: any pre-existing c1 schema aborts atomically.
CREATE SCHEMA c1 AUTHORIZATION c1_owner;
SET LOCAL ROLE c1_owner;
REVOKE ALL ON SCHEMA c1 FROM PUBLIC;

-- Organization belongs to the channel. is_holdout has no default: every
-- organization needs an explicit decision, and the flag is locked after insert.
CREATE TABLE c1.organizations (
  organization_id text PRIMARY KEY CHECK (organization_id ~ '^[a-z0-9_]{1,64}$'),
  name text NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
  country text NOT NULL CHECK (country ~ '^[A-Z]{2}$'),
  is_holdout boolean NOT NULL
);

CREATE TABLE c1.cohorts (
  cohort_id text NOT NULL, version text NOT NULL,
  manifest_hash text NOT NULL CHECK (manifest_hash ~ '^[0-9a-f]{64}$'),
  channel_ids text[] NOT NULL CHECK (cardinality(channel_ids) > 0 AND array_position(channel_ids, NULL) IS NULL),
  approval_status text NOT NULL DEFAULT 'pending' CHECK (approval_status IN ('pending','approved','rejected')),
  approved_by text, approved_at timestamptz, approval_reference text,
  enabled boolean NOT NULL DEFAULT false,
  total_attempt_budget integer CHECK (total_attempt_budget > 0),
  discovery_attempt_budget integer CHECK (discovery_attempt_budget >= 0),
  candidate_attempt_reserve integer CHECK (candidate_attempt_reserve >= 0),
  max_pages_per_channel integer CHECK (max_pages_per_channel BETWEEN 1 AND 200),
  -- New videos are admitted only if published on/after (first run - lookback).
  admission_lookback_days integer NOT NULL DEFAULT 30 CHECK (admission_lookback_days BETWEEN 0 AND 365),
  schedule_timezone text NOT NULL DEFAULT 'Asia/Colombo',
  proposed_local_time time NOT NULL DEFAULT '02:00',
  retention_decision_reference text,
  PRIMARY KEY (cohort_id, version),
  CHECK (approval_status <> 'approved' OR
    (approved_by IS NOT NULL AND approved_at IS NOT NULL AND approval_reference IS NOT NULL)),
  CHECK (NOT enabled OR (approval_status = 'approved' AND
    retention_decision_reference IS NOT NULL AND total_attempt_budget IS NOT NULL AND
    discovery_attempt_budget IS NOT NULL AND candidate_attempt_reserve IS NOT NULL AND
    max_pages_per_channel IS NOT NULL AND
    discovery_attempt_budget + candidate_attempt_reserve <= total_attempt_budget))
);

CREATE UNIQUE INDEX one_enabled_version_per_cohort ON c1.cohorts (cohort_id) WHERE enabled;

-- One row per YouTube channel, independent of cohort versions.
CREATE TABLE c1.channels (
  channel_id text PRIMARY KEY CHECK (channel_id ~ '^[A-Za-z0-9_.-]{1,128}$'),
  organization_id text NOT NULL REFERENCES c1.organizations ON DELETE RESTRICT,
  admitted_at timestamptz NOT NULL, admission_source text NOT NULL,
  channel_name text, uploads_playlist_id text, published_at timestamptz,
  country text CHECK (country ~ '^[A-Z]{2}$'),
  default_language text CHECK (default_language ~ '^[A-Za-z]{2,3}(-[A-Za-z0-9]{1,8}){0,3}$'),
  topic_categories text[] CHECK (topic_categories IS NULL OR
    (cardinality(topic_categories) <= 10 AND array_position(topic_categories, NULL) IS NULL)),
  metadata_observed_at timestamptz
);

-- Role belongs to cohort membership, so one channel can be owned in one study
-- and a generalization test in another. Membership rows are immutable.
CREATE TABLE c1.cohort_channels (
  cohort_id text NOT NULL, version text NOT NULL,
  channel_id text NOT NULL REFERENCES c1.channels ON DELETE RESTRICT,
  role text NOT NULL CHECK (role IN ('owned','competitor','generalization_test')),
  admitted_at timestamptz NOT NULL,
  PRIMARY KEY (cohort_id, version, channel_id),
  FOREIGN KEY (cohort_id, version) REFERENCES c1.cohorts ON DELETE RESTRICT
);

-- One row per video, independent of cohort versions.
CREATE TABLE c1.videos (
  video_id text PRIMARY KEY CHECK (video_id ~ '^[A-Za-z0-9_.-]{1,128}$'),
  channel_id text NOT NULL REFERENCES c1.channels ON DELETE RESTRICT,
  admitted_at timestamptz NOT NULL, admission_source text NOT NULL,
  inventory_revision bigint NOT NULL CHECK (inventory_revision >= 0),
  title text, published_at timestamptz,
  duration_seconds bigint CHECK (duration_seconds >= 0),
  category_id text CHECK (category_id ~ '^[A-Za-z0-9_.-]{1,128}$'),
  metadata_observed_at timestamptz,
  UNIQUE (video_id, channel_id)
);

CREATE TABLE c1.collection_runs (
  run_id uuid PRIMARY KEY,
  cohort_id text NOT NULL, version text NOT NULL,
  manifest_hash text NOT NULL CHECK (manifest_hash ~ '^[0-9a-f]{64}$'),
  scheduled_for timestamptz NOT NULL, collection_date date NOT NULL,
  inventory_revision bigint NOT NULL CHECK (inventory_revision >= 0),
  inventory_cutoff timestamptz NOT NULL, started_at timestamptz NOT NULL,
  deadline_at timestamptz NOT NULL CHECK (deadline_at > started_at),
  phase text NOT NULL CHECK (phase IN ('refresh','channels','discovery','candidates','finished')),
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','running','complete','partial','failed')),
  heartbeat_at timestamptz, ended_at timestamptz,
  attempts_reserved integer NOT NULL DEFAULT 0 CHECK (attempts_reserved >= 0),
  discovery_attempts integer NOT NULL DEFAULT 0 CHECK (discovery_attempts >= 0),
  inventory_complete boolean NOT NULL DEFAULT false,
  discovery_complete boolean NOT NULL DEFAULT false,
  summary jsonb NOT NULL DEFAULT '{}', failure_code text,
  UNIQUE (cohort_id, version, scheduled_for),
  UNIQUE (run_id, cohort_id, version),
  FOREIGN KEY (cohort_id, version) REFERENCES c1.cohorts ON DELETE RESTRICT
);
CREATE UNIQUE INDEX one_active_run_per_cohort ON c1.collection_runs (cohort_id, version)
  WHERE status IN ('pending','running');

-- A real coordination entity: no fake run_id/work_key and no nullable task FK.
-- Deployment/bootstrap operator pre-creates one row per cohort version.
CREATE TABLE c1.collection_coordination (
  cohort_id text NOT NULL, version text NOT NULL,
  active_run_id uuid, lease_owner uuid, lease_expires_at timestamptz,
  fence bigint NOT NULL DEFAULT 0 CHECK (fence >= 0),
  inventory_revision bigint NOT NULL DEFAULT 0 CHECK (inventory_revision >= 0),
  discovery_start_offset integer NOT NULL DEFAULT 0 CHECK (discovery_start_offset >= 0),
  -- Set once by the first run: its scheduled time minus admission_lookback_days.
  admission_published_after timestamptz,
  PRIMARY KEY (cohort_id, version),
  FOREIGN KEY (cohort_id, version) REFERENCES c1.cohorts ON DELETE RESTRICT,
  FOREIGN KEY (active_run_id, cohort_id, version)
    REFERENCES c1.collection_runs (run_id, cohort_id, version) ON DELETE RESTRICT,
  CHECK ((lease_owner IS NULL) = (lease_expires_at IS NULL)),
  CHECK (lease_owner IS NULL OR active_run_id IS NOT NULL)
);

CREATE TABLE c1.collection_work (
  work_id uuid PRIMARY KEY, run_id uuid NOT NULL,
  cohort_id text NOT NULL, version text NOT NULL, work_key text NOT NULL,
  phase text NOT NULL CHECK (phase IN ('refresh','channels','discovery','candidates')),
  channel_id text, selected_ids text[] NOT NULL DEFAULT '{}',
  dispatch_order bigint NOT NULL CHECK (dispatch_order >= 0),
  input_cursor text, output_cursor text, seen_tokens text[] NOT NULL DEFAULT '{}',
  page_count integer NOT NULL DEFAULT 0 CHECK (page_count >= 0),
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','claimed','staged','committed','failed','deferred')),
  lease_owner uuid, lease_expires_at timestamptz,
  fence bigint NOT NULL DEFAULT 0 CHECK (fence >= 0),
  next_attempt_at timestamptz, attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  staged_response jsonb, observed_at timestamptz, payload_hash text,
  outcomes jsonb NOT NULL DEFAULT '{}', failure_code text,
  UNIQUE (run_id, work_key), UNIQUE (work_id, run_id, cohort_id, version),
  FOREIGN KEY (run_id, cohort_id, version) REFERENCES c1.collection_runs (run_id, cohort_id, version) ON DELETE RESTRICT,
  FOREIGN KEY (cohort_id, version, channel_id) REFERENCES c1.cohort_channels ON DELETE RESTRICT,
  CHECK (cardinality(selected_ids) <= 50 AND array_position(selected_ids, NULL) IS NULL),
  CHECK (phase <> 'discovery' OR (channel_id IS NOT NULL AND cardinality(selected_ids) = 0)),
  CHECK ((lease_owner IS NULL) = (lease_expires_at IS NULL)),
  CHECK ((staged_response IS NULL AND observed_at IS NULL AND payload_hash IS NULL) OR
    (staged_response IS NOT NULL AND observed_at IS NOT NULL AND payload_hash IS NOT NULL AND payload_hash ~ '^[0-9a-f]{64}$')),
  CHECK (staged_response IS NULL OR octet_length(staged_response::text) <= 262144),
  CHECK (octet_length(outcomes::text) <= 65536)
);
CREATE INDEX work_ready ON c1.collection_work (status, next_attempt_at, dispatch_order);
CREATE INDEX runs_scheduled ON c1.collection_runs (scheduled_for, status);
CREATE INDEX videos_owner ON c1.videos (channel_id, published_at);
CREATE INDEX cohort_channels_channel ON c1.cohort_channels (channel_id);

-- Snapshots are keyed by entity and observation time only. cohort_id/version,
-- run_id and work_id are provenance, so new cohort versions never split a series.
CREATE TABLE c1.channel_stats_history (
  channel_id text NOT NULL REFERENCES c1.channels ON DELETE RESTRICT,
  observed_at timestamptz NOT NULL,
  cohort_id text NOT NULL, version text NOT NULL, run_id uuid NOT NULL, work_id uuid NOT NULL,
  subscriber_count bigint CHECK (subscriber_count >= 0),
  view_count bigint CHECK (view_count >= 0), video_count bigint CHECK (video_count >= 0),
  payload_hash text NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
  PRIMARY KEY (channel_id, observed_at),
  UNIQUE (channel_id, run_id),
  FOREIGN KEY (work_id, run_id, cohort_id, version)
    REFERENCES c1.collection_work (work_id, run_id, cohort_id, version) ON DELETE RESTRICT
);
CREATE TABLE c1.video_stats_history (
  video_id text NOT NULL, channel_id text NOT NULL,
  observed_at timestamptz NOT NULL,
  cohort_id text NOT NULL, version text NOT NULL, run_id uuid NOT NULL, work_id uuid NOT NULL,
  view_count bigint CHECK (view_count >= 0), like_count bigint CHECK (like_count >= 0),
  comment_count bigint CHECK (comment_count >= 0),
  payload_hash text NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
  PRIMARY KEY (video_id, observed_at),
  UNIQUE (video_id, run_id),
  FOREIGN KEY (video_id, channel_id) REFERENCES c1.videos (video_id, channel_id) ON DELETE RESTRICT,
  FOREIGN KEY (work_id, run_id, cohort_id, version)
    REFERENCES c1.collection_work (work_id, run_id, cohort_id, version) ON DELETE RESTRICT
);
CREATE INDEX video_history_channel ON c1.video_stats_history (channel_id, observed_at);
CREATE TABLE c1.schema_migrations (
  version text PRIMARY KEY, checksum text NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
  applied_at timestamptz NOT NULL DEFAULT now()
);

-- Invoker-only integrity triggers also protect against accidental operator DML.
CREATE FUNCTION c1.guard_inventory() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER
SET search_path = pg_catalog AS $$
DECLARE mutable_columns text[];
BEGIN
  IF TG_TABLE_NAME = 'channels' THEN
    mutable_columns := ARRAY['channel_name','uploads_playlist_id','published_at','country',
      'default_language','topic_categories','metadata_observed_at'];
  ELSE
    mutable_columns := ARRAY['title','published_at','duration_seconds','category_id',
      'metadata_observed_at'];
  END IF;
  -- Locks channel_id/organization_id and video_id/channel_id plus admission fields.
  IF (to_jsonb(NEW) - mutable_columns) IS DISTINCT FROM (to_jsonb(OLD) - mutable_columns) THEN
    RAISE EXCEPTION 'C1 immutable inventory identity/admission fields';
  END IF;
  IF OLD.metadata_observed_at IS NOT NULL AND
    (NEW.metadata_observed_at IS NULL OR NEW.metadata_observed_at < OLD.metadata_observed_at) THEN
    RAISE EXCEPTION 'C1 metadata timestamp cannot move backwards';
  END IF;
  RETURN NEW;
END; $$;
CREATE TRIGGER guard_channels BEFORE UPDATE ON c1.channels
  FOR EACH ROW EXECUTE FUNCTION c1.guard_inventory();
CREATE TRIGGER guard_videos BEFORE UPDATE ON c1.videos
  FOR EACH ROW EXECUTE FUNCTION c1.guard_inventory();

CREATE FUNCTION c1.guard_membership() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER
SET search_path = pg_catalog AS $$
BEGIN
  IF TG_OP = 'UPDATE' THEN
    RAISE EXCEPTION 'C1 cohort membership is immutable';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM c1.cohorts c WHERE c.cohort_id = NEW.cohort_id
    AND c.version = NEW.version AND NEW.channel_id = ANY(c.channel_ids)) THEN
    RAISE EXCEPTION 'C1 channel outside cohort allowlist';
  END IF;
  RETURN NEW;
END; $$;
CREATE TRIGGER guard_membership BEFORE INSERT OR UPDATE ON c1.cohort_channels
  FOR EACH ROW EXECUTE FUNCTION c1.guard_membership();

CREATE FUNCTION c1.guard_organization() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER
SET search_path = pg_catalog AS $$
BEGIN
  IF (NEW.organization_id, NEW.is_holdout) IS DISTINCT FROM (OLD.organization_id, OLD.is_holdout) THEN
    RAISE EXCEPTION 'C1 organization identity and holdout flag are immutable';
  END IF;
  RETURN NEW;
END; $$;
CREATE TRIGGER guard_organization BEFORE UPDATE ON c1.organizations
  FOR EACH ROW EXECUTE FUNCTION c1.guard_organization();

CREATE FUNCTION c1.guard_coordination() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER
SET search_path = pg_catalog AS $$
BEGIN
  IF OLD.admission_published_after IS NOT NULL AND
    NEW.admission_published_after IS DISTINCT FROM OLD.admission_published_after THEN
    RAISE EXCEPTION 'C1 admission cutoff is set once';
  END IF;
  RETURN NEW;
END; $$;
CREATE TRIGGER guard_coordination BEFORE UPDATE ON c1.collection_coordination
  FOR EACH ROW EXECUTE FUNCTION c1.guard_coordination();

CREATE FUNCTION c1.guard_work() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER
SET search_path = pg_catalog AS $$
BEGIN
  IF OLD.observed_at IS NOT NULL AND
    (NEW.observed_at, NEW.payload_hash, NEW.staged_response) IS DISTINCT FROM
    (OLD.observed_at, OLD.payload_hash, OLD.staged_response) THEN
    RAISE EXCEPTION 'C1 staged observation is immutable';
  END IF;
  RETURN NEW;
END; $$;
CREATE TRIGGER guard_work BEFORE UPDATE ON c1.collection_work
  FOR EACH ROW EXECUTE FUNCTION c1.guard_work();

CREATE FUNCTION c1.guard_operational_identity() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER
SET search_path = pg_catalog AS $$
DECLARE mutable_columns text[];
BEGIN
  IF TG_TABLE_NAME = 'collection_runs' THEN
    mutable_columns := ARRAY['phase','status','heartbeat_at','ended_at','attempts_reserved',
      'discovery_attempts','inventory_complete','discovery_complete','summary','failure_code'];
  ELSE
    mutable_columns := ARRAY['output_cursor','seen_tokens','page_count','status','lease_owner',
      'lease_expires_at','fence','next_attempt_at','attempts','staged_response','observed_at',
      'payload_hash','outcomes','failure_code'];
  END IF;
  IF (to_jsonb(NEW) - mutable_columns) IS DISTINCT FROM (to_jsonb(OLD) - mutable_columns) THEN
    RAISE EXCEPTION 'C1 immutable run/work definition';
  END IF;
  RETURN NEW;
END; $$;
CREATE TRIGGER guard_run_identity BEFORE UPDATE ON c1.collection_runs
  FOR EACH ROW EXECUTE FUNCTION c1.guard_operational_identity();
CREATE TRIGGER guard_work_identity BEFORE UPDATE ON c1.collection_work
  FOR EACH ROW EXECUTE FUNCTION c1.guard_operational_identity();

-- Model-facing views. Owner-rights (security_invoker = false) so readers need
-- SELECT on the view only and never on base tables; security_barrier stops
-- reader-supplied predicates from seeing rows before the holdout filter.
-- The two bodies are identical except for the opposite is_holdout filter.
CREATE VIEW c1.training_observations WITH (security_barrier = true, security_invoker = false) AS
SELECT h.video_id, h.channel_id, ch.organization_id, h.observed_at, h.run_id,
  h.view_count, h.like_count, h.comment_count,
  v.published_at, v.duration_seconds, v.category_id,
  cs.observed_at AS channel_observed_at, cs.subscriber_count,
  cs.view_count AS channel_view_count, cs.video_count AS channel_video_count
FROM c1.video_stats_history h
JOIN c1.videos v ON v.video_id = h.video_id
JOIN c1.channels ch ON ch.channel_id = h.channel_id
JOIN c1.organizations o ON o.organization_id = ch.organization_id
LEFT JOIN c1.channel_stats_history cs ON cs.channel_id = h.channel_id AND cs.run_id = h.run_id
WHERE o.is_holdout = false;

CREATE VIEW c1.evaluation_observations WITH (security_barrier = true, security_invoker = false) AS
SELECT h.video_id, h.channel_id, ch.organization_id, h.observed_at, h.run_id,
  h.view_count, h.like_count, h.comment_count,
  v.published_at, v.duration_seconds, v.category_id,
  cs.observed_at AS channel_observed_at, cs.subscriber_count,
  cs.view_count AS channel_view_count, cs.video_count AS channel_video_count
FROM c1.video_stats_history h
JOIN c1.videos v ON v.video_id = h.video_id
JOIN c1.channels ch ON ch.channel_id = h.channel_id
JOIN c1.organizations o ON o.organization_id = ch.organization_id
LEFT JOIN c1.channel_stats_history cs ON cs.channel_id = h.channel_id AND cs.run_id = h.run_id
WHERE o.is_holdout = true;

REVOKE ALL ON ALL TABLES IN SCHEMA c1 FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA c1 FROM PUBLIC;
COMMIT;
