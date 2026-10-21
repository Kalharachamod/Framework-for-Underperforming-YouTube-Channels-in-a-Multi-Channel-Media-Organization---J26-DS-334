-- Run as postgres (Supabase-like) after the enabled phase. Read checks, then
-- owner-path history guard probes that all roll back.
BEGIN;
SET LOCAL ROLE c1_owner;
SELECT 'collection_runs.summary' AS col, jsonb_typeof(summary) AS typ, count(*) AS n
  FROM c1.collection_runs GROUP BY 2
UNION ALL
SELECT 'collection_work.outcomes', jsonb_typeof(outcomes), count(*)
  FROM c1.collection_work GROUP BY 2
UNION ALL
SELECT 'collection_work.staged_response', jsonb_typeof(staged_response), count(*)
  FROM c1.collection_work WHERE staged_response IS NOT NULL GROUP BY 2
ORDER BY 1, 2;
SELECT status, count(*) AS work_rows FROM c1.collection_work GROUP BY 1 ORDER BY 1;
SELECT
  (SELECT count(*) FROM c1.channel_stats_history) AS channel_history,
  (SELECT count(DISTINCT channel_id) FROM c1.channel_stats_history) AS channels,
  (SELECT count(*) FROM c1.video_stats_history) AS video_history,
  (SELECT count(DISTINCT video_id) FROM c1.video_stats_history) AS videos_observed,
  (SELECT count(*) FROM c1.videos) AS videos,
  (SELECT string_agg(status, ',') FROM c1.collection_runs) AS run_status;
DO $t$
DECLARE s text;
BEGIN
  FOREACH s IN ARRAY ARRAY[
    'UPDATE c1.video_stats_history SET view_count = 0',
    'DELETE FROM c1.video_stats_history',
    'TRUNCATE c1.channel_stats_history'] LOOP
    BEGIN
      EXECUTE s;
      RAISE EXCEPTION 'FAIL owner: % succeeded', s;
    EXCEPTION WHEN raise_exception THEN
      IF SQLERRM LIKE 'FAIL%' THEN RAISE; END IF;
      RAISE NOTICE 'PASS owner: % -> %', s, SQLERRM;
    END;
  END LOOP;
END $t$;
ROLLBACK;
