-- 0004_comment_replies.sql
-- Schema 1.3: comment replies and edit time (shared/schemas/entities.py).
-- Additive: existing rows stay valid (top-level comments, never edited).
--
-- parent_comment_id has no foreign key on purpose: a reply and its parent are
-- written in the same batch in any order. The collector stores replies only
-- together with a valid parent, and the quality check reports orphan replies.

ALTER TABLE research.comments ADD COLUMN IF NOT EXISTS parent_comment_id text
    CHECK (parent_comment_id IS NULL OR parent_comment_id ~ '^[A-Za-z0-9_.-]{1,128}$');
ALTER TABLE research.comments ADD COLUMN IF NOT EXISTS edited_at timestamptz;

-- Replies of a thread (Component 3: reply interactions).
CREATE INDEX IF NOT EXISTS comments_parent_idx ON research.comments (parent_comment_id)
    WHERE parent_comment_id IS NOT NULL;
