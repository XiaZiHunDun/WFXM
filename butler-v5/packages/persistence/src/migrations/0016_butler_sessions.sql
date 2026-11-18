-- P4.2: durable butler sessions.
-- The butler runtime keeps its own transcript here; memory is only a
-- projection over these rows, never their replacement.
CREATE TABLE IF NOT EXISTS butler_sessions (
  conversation_id text PRIMARY KEY NOT NULL,
  user_id text NOT NULL,
  project_id text,
  messages jsonb NOT NULL,
  summary text,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);
