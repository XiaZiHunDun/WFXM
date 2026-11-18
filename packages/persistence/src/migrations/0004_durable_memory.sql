-- Durable Memory baseline (DESIGN §9 layer 2). Not Transcript; no embedding.
CREATE TABLE IF NOT EXISTS durable_memories (
  memory_id uuid PRIMARY KEY NOT NULL,
  subject text NOT NULL,
  content text NOT NULL,
  source_kind text NOT NULL,
  status text NOT NULL,
  confidence double precision NOT NULL,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  expires_at timestamptz,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  confirmed_at timestamptz
);

CREATE INDEX IF NOT EXISTS durable_memories_subject_status_idx
  ON durable_memories (subject, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS durable_memories_expires_idx
  ON durable_memories (expires_at)
  WHERE expires_at IS NOT NULL;
