-- REVIEW ONLY. Apply after 001, as separately authorized deployment operator.
-- Collector receives no membership in c1_owner. No existing ACL is revoked.
BEGIN;
SET LOCAL ROLE c1_owner;
GRANT USAGE ON SCHEMA c1 TO c1_collector;
GRANT SELECT ON c1.cohorts, c1.organizations, c1.cohort_channels TO c1_collector;
-- Channels are added only by the reviewed bootstrap; the collector updates metadata.
GRANT SELECT ON c1.channels TO c1_collector;
GRANT SELECT, INSERT ON c1.videos, c1.channel_stats_history,
  c1.video_stats_history, c1.collection_runs, c1.collection_work TO c1_collector;
GRANT SELECT ON c1.collection_coordination TO c1_collector;
GRANT UPDATE (channel_name, uploads_playlist_id, published_at, country, default_language,
  topic_categories, metadata_observed_at) ON c1.channels TO c1_collector;
GRANT UPDATE (title, published_at, duration_seconds, category_id, metadata_observed_at)
  ON c1.videos TO c1_collector;
GRANT UPDATE (phase, status, heartbeat_at, ended_at, attempts_reserved,
  discovery_attempts, inventory_complete, discovery_complete, summary, failure_code)
  ON c1.collection_runs TO c1_collector;
GRANT UPDATE (output_cursor, seen_tokens, page_count, status, lease_owner,
  lease_expires_at, fence, next_attempt_at, attempts, staged_response, observed_at,
  payload_hash, outcomes, failure_code) ON c1.collection_work TO c1_collector;
GRANT UPDATE (active_run_id, lease_owner, lease_expires_at, fence,
  inventory_revision, discovery_start_offset, admission_published_after)
  ON c1.collection_coordination TO c1_collector;
-- No runtime INSERT on coordination: operator pre-creates a real cohort row.
-- No runtime privilege on c1.schema_migrations; no sequences or definer routines.

-- Model code reads only these owner-rights views, never the base tables.
GRANT USAGE ON SCHEMA c1 TO c1_model_reader;
GRANT SELECT ON c1.training_observations, c1.evaluation_observations TO c1_model_reader;

ALTER DEFAULT PRIVILEGES FOR ROLE c1_owner IN SCHEMA c1 REVOKE ALL ON TABLES FROM PUBLIC;
-- Function default privileges are global; do not change those. Explicitly
-- revoke PUBLIC EXECUTE on every new C1 function in its creation transaction.

ALTER TABLE c1.organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE c1.cohorts ENABLE ROW LEVEL SECURITY;
ALTER TABLE c1.channels ENABLE ROW LEVEL SECURITY;
ALTER TABLE c1.cohort_channels ENABLE ROW LEVEL SECURITY;
ALTER TABLE c1.videos ENABLE ROW LEVEL SECURITY;
ALTER TABLE c1.channel_stats_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE c1.video_stats_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE c1.collection_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE c1.collection_work ENABLE ROW LEVEL SECURITY;
ALTER TABLE c1.collection_coordination ENABLE ROW LEVEL SECURITY;
ALTER TABLE c1.schema_migrations ENABLE ROW LEVEL SECURITY;

-- Cohort configuration is visible even while disabled to explain a closed gate.
CREATE POLICY collector_read_config ON c1.cohorts FOR SELECT TO c1_collector USING (true);
CREATE POLICY collector_read_config ON c1.organizations FOR SELECT TO c1_collector USING (true);
CREATE POLICY collector_read_config ON c1.cohort_channels FOR SELECT TO c1_collector USING (true);

-- Reads of application data are permitted while disabled for diagnosis;
-- mutation requires an approved/enabled cohort on every statement.
CREATE POLICY collector_read ON c1.channels FOR SELECT TO c1_collector USING (true);
CREATE POLICY collector_read ON c1.videos FOR SELECT TO c1_collector USING (true);
CREATE POLICY collector_read ON c1.channel_stats_history FOR SELECT TO c1_collector USING (true);
CREATE POLICY collector_read ON c1.video_stats_history FOR SELECT TO c1_collector USING (true);
CREATE POLICY collector_read ON c1.collection_runs FOR SELECT TO c1_collector USING (true);
CREATE POLICY collector_read ON c1.collection_work FOR SELECT TO c1_collector USING (true);
CREATE POLICY collector_read ON c1.collection_coordination FOR SELECT TO c1_collector USING (true);

-- Policy generation is confined to enumerated NEW c1 tables. Bare CREATE POLICY
-- and transaction rollback deliberately reject repeat/incompatible application.
DO $policies$
DECLARE t text; gate text;
BEGIN
  FOREACH t IN ARRAY ARRAY['channels','videos','channel_stats_history','video_stats_history',
    'collection_runs','collection_work','collection_coordination'] LOOP
    IF t IN ('channels','videos') THEN
      -- Entity rows: the channel must be a member of an approved, enabled cohort.
      gate := format('EXISTS (SELECT 1 FROM c1.cohort_channels m JOIN c1.cohorts c ON c.cohort_id = m.cohort_id AND c.version = m.version WHERE m.channel_id = %I.channel_id AND c.enabled AND c.approval_status = ''approved'')', t);
    ELSIF t IN ('channel_stats_history','video_stats_history') THEN
      -- Observations: same membership, and the provenance must name that cohort.
      gate := format('EXISTS (SELECT 1 FROM c1.cohort_channels m JOIN c1.cohorts c ON c.cohort_id = m.cohort_id AND c.version = m.version WHERE m.channel_id = %I.channel_id AND m.cohort_id = %I.cohort_id AND m.version = %I.version AND c.enabled AND c.approval_status = ''approved'')', t, t, t);
    ELSE
      gate := format('EXISTS (SELECT 1 FROM c1.cohorts c WHERE c.cohort_id = %I.cohort_id AND c.version = %I.version AND c.enabled AND c.approval_status = ''approved'')', t, t);
    END IF;
    IF t = 'collection_runs' THEN
      gate := gate || ' AND EXISTS (SELECT 1 FROM c1.cohorts c WHERE c.cohort_id = collection_runs.cohort_id AND c.version = collection_runs.version AND c.manifest_hash = collection_runs.manifest_hash)';
    END IF;
    IF t NOT IN ('channels','collection_coordination') THEN
      EXECUTE format('CREATE POLICY collector_insert ON c1.%I FOR INSERT TO c1_collector WITH CHECK (%s)', t, gate);
    END IF;
    IF t NOT IN ('channel_stats_history','video_stats_history') THEN
      EXECUTE format('CREATE POLICY collector_update ON c1.%I FOR UPDATE TO c1_collector USING (%s) WITH CHECK (%s)', t, gate, gate);
    END IF;
  END LOOP;
END; $policies$;
COMMIT;

-- DATABASE CONNECT: separately reviewed, additive grant only, executed by the
-- authorized administrative actor (not c1_owner). No CREATE/TEMP grant.
BEGIN;
DO $connect$
BEGIN
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO c1_collector, c1_model_reader', current_database());
END; $connect$;
COMMIT;
