BEGIN READ ONLY;
-- Panel demo: read-only summary of collected C1 data. Run with psql as c1_collector
-- (see research/component_1/README.md). SELECT only on tables 002b_access.sql
-- grants to c1_collector; the transaction is always rolled back. Times are shown
-- in Asia/Colombo. No credentials here.
SET LOCAL statement_timeout = '30s';
\pset pager off
\pset border 2
\pset null '-'
\pset numericlocale on

\echo
\echo '=== 1. Overview ==='
\x on
SELECT
  (SELECT count(*) FROM c1.channels) AS "Channels",
  (SELECT count(*) FROM c1.videos) AS "Videos",
  (SELECT count(*) FROM c1.channel_stats_history) AS "Channel snapshots",
  (SELECT count(*) FROM c1.video_stats_history) AS "Video snapshots",
  to_char(least(
    (SELECT min(observed_at) FROM c1.channel_stats_history),
    (SELECT min(observed_at) FROM c1.video_stats_history)
  ) AT TIME ZONE 'Asia/Colombo', 'YYYY-MM-DD HH24:MI') AS "First observation (Colombo)",
  to_char(greatest(
    (SELECT max(observed_at) FROM c1.channel_stats_history),
    (SELECT max(observed_at) FROM c1.video_stats_history)
  ) AT TIME ZONE 'Asia/Colombo', 'YYYY-MM-DD HH24:MI') AS "Latest observation (Colombo)";
\x off

\echo
\echo '=== 2. Latest snapshot per channel ==='
-- Role comes from membership in the approved, enabled cohort version.
WITH membership AS (
  SELECT m.channel_id, m.role
  FROM c1.cohort_channels m
  JOIN c1.cohorts c ON c.cohort_id = m.cohort_id AND c.version = m.version
  WHERE c.enabled AND c.approval_status = 'approved'
)
SELECT ch.channel_name AS "Channel",
  o.name AS "Organization",
  m.role AS "Role",
  s.subscriber_count AS "Subscribers",
  s.view_count AS "Total views",
  s.video_count AS "Videos",
  to_char(s.observed_at AT TIME ZONE 'Asia/Colombo', 'YYYY-MM-DD HH24:MI') AS "Observed (Colombo)"
FROM membership m
JOIN c1.channels ch ON ch.channel_id = m.channel_id
JOIN c1.organizations o ON o.organization_id = ch.organization_id
LEFT JOIN LATERAL (
  SELECT h.subscriber_count, h.view_count, h.video_count, h.observed_at
  FROM c1.channel_stats_history h
  WHERE h.channel_id = ch.channel_id
  ORDER BY h.observed_at DESC
  LIMIT 1
) s ON true
ORDER BY o.name, s.subscriber_count DESC NULLS LAST, ch.channel_name;

\echo
\echo '=== 3. Top 15 videos by latest view count ==='
WITH latest AS (
  SELECT DISTINCT ON (h.video_id) h.video_id, h.view_count, h.like_count, h.comment_count
  FROM c1.video_stats_history h
  ORDER BY h.video_id, h.observed_at DESC
)
SELECT CASE WHEN length(v.title) > 60 THEN left(v.title, 57) || '...' ELSE v.title END AS "Title",
  ch.channel_name AS "Channel",
  to_char(v.published_at AT TIME ZONE 'Asia/Colombo', 'YYYY-MM-DD') AS "Published (Colombo)",
  CASE WHEN v.duration_seconds IS NOT NULL THEN
    (v.duration_seconds / 60) || ':' || lpad((v.duration_seconds % 60)::text, 2, '0')
  END AS "Duration (mm:ss)",
  l.view_count AS "Views",
  l.like_count AS "Likes",
  l.comment_count AS "Comments"
FROM latest l
JOIN c1.videos v ON v.video_id = l.video_id
JOIN c1.channels ch ON ch.channel_id = v.channel_id
ORDER BY l.view_count DESC NULLS LAST, v.video_id
LIMIT 15;

\echo
\echo '=== 4. Snapshots per collection day (Asia/Colombo) ==='
WITH channel_days AS (
  SELECT (observed_at AT TIME ZONE 'Asia/Colombo')::date AS day,
    count(*) AS snapshots, count(DISTINCT channel_id) AS entities
  FROM c1.channel_stats_history
  GROUP BY 1
), video_days AS (
  SELECT (observed_at AT TIME ZONE 'Asia/Colombo')::date AS day,
    count(*) AS snapshots, count(DISTINCT video_id) AS entities
  FROM c1.video_stats_history
  GROUP BY 1
)
SELECT to_char(coalesce(c.day, v.day), 'YYYY-MM-DD Dy') AS "Collection day",
  coalesce(c.snapshots, 0) AS "Channel snapshots",
  coalesce(c.entities, 0) AS "Channels observed",
  coalesce(v.snapshots, 0) AS "Video snapshots",
  coalesce(v.entities, 0) AS "Videos observed"
FROM channel_days c
FULL JOIN video_days v ON v.day = c.day
ORDER BY coalesce(c.day, v.day);

ROLLBACK;
