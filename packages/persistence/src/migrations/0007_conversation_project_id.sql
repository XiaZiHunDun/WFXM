-- Multi-project: index conversations by project_id (derived from conversation_id at write/backfill).
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS project_id text;
CREATE INDEX IF NOT EXISTS conversations_project_idx ON conversations (project_id, updated_at DESC);
