-- Component 2 pilot dataset extraction reference.
--
-- Original Supabase sources:
--   research.comments
--   research.videos
--   research.channels
--
-- Sampling method recorded for reproducibility:
--   - Up to 400 non-empty comments per selected channel
--   - Selection spread across videos before deterministic sampling
--   - Deterministic MD5(comment_id) ordering
--   - Empty comment text excluded
--
-- Exact channel-selection criteria and final export command are currently unknown.
-- Fill in the confirmed SQL from the Supabase SQL Editor when available.

-- Reference pattern only; verify table/column names before reuse.
with eligible_comments as (
  select
    c.comment_id,
    c.channel_id,
    ch.channel_name,
    c.video_id,
    c.comment_text,
    c.published_at,
    c.edited_at,
    c.like_count,
    c.parent_comment_id,
    row_number() over (
      partition by c.channel_id
      order by md5(c.comment_id)
    ) as channel_sample_rank
  from research.comments c
  left join research.channels ch on ch.channel_id = c.channel_id
  where c.comment_text is not null
    and btrim(c.comment_text) <> ''
)
select *
from eligible_comments
where channel_sample_rank <= 400;
