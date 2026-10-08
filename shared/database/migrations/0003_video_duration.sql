-- 0003_video_duration.sql
-- Schema 1.2: optional video length in seconds (shared/schemas/entities.py).
-- Additive: existing rows stay valid (NULL until the next collection).

ALTER TABLE research.videos ADD COLUMN IF NOT EXISTS duration_seconds bigint CHECK (duration_seconds >= 0);
