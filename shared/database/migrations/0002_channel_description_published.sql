-- 0002_channel_description_published.sql
-- Schema 1.1: optional channel description and creation date (shared/schemas/entities.py).
-- Additive: existing rows stay valid (NULL until the next collection).

ALTER TABLE research.channels ADD COLUMN IF NOT EXISTS description  text;
ALTER TABLE research.channels ADD COLUMN IF NOT EXISTS published_at timestamptz;  -- channel created on YouTube
