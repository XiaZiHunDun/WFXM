-- Target runtime relational model (additive; does not modify 0001 tables).
CREATE TABLE IF NOT EXISTS conversations (
  conversation_id text PRIMARY KEY NOT NULL,
  subject text NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
  message_id uuid PRIMARY KEY NOT NULL,
  conversation_id text NOT NULL REFERENCES conversations (conversation_id),
  role text NOT NULL,
  content jsonb NOT NULL,
  trigger_source text,
  idempotency_key text,
  created_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS messages_conversation_idx ON messages (conversation_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS messages_idempotency_uniq
  ON messages (idempotency_key)
  WHERE idempotency_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS runs (
  run_id uuid PRIMARY KEY NOT NULL,
  conversation_id text NOT NULL REFERENCES conversations (conversation_id),
  parent_run_id uuid REFERENCES runs (run_id),
  trigger_source text NOT NULL,
  idempotency_key text NOT NULL,
  subject text NOT NULL,
  goal text NOT NULL,
  status text NOT NULL,
  budget jsonb NOT NULL,
  deadline timestamptz,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS runs_idempotency_uniq ON runs (idempotency_key);
CREATE INDEX IF NOT EXISTS runs_conversation_idx ON runs (conversation_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS runs_one_active_main_uniq
  ON runs (conversation_id)
  WHERE parent_run_id IS NULL
    AND status IN ('queued', 'running', 'waiting_approval', 'waiting_external');

CREATE TABLE IF NOT EXISTS steps (
  step_id uuid PRIMARY KEY NOT NULL,
  run_id uuid NOT NULL REFERENCES runs (run_id),
  kind text NOT NULL,
  status text NOT NULL,
  input jsonb NOT NULL,
  output jsonb,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS steps_run_idx ON steps (run_id, created_at);

CREATE TABLE IF NOT EXISTS scoped_grants (
  grant_id uuid PRIMARY KEY NOT NULL,
  run_id uuid NOT NULL REFERENCES runs (run_id),
  subject text NOT NULL,
  scope jsonb NOT NULL,
  remaining_uses integer,
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS scoped_grants_run_idx ON scoped_grants (run_id, expires_at);

CREATE TABLE IF NOT EXISTS audit_events (
  audit_id uuid PRIMARY KEY NOT NULL,
  run_id uuid,
  conversation_id text,
  action text NOT NULL,
  subject text NOT NULL,
  detail jsonb NOT NULL,
  created_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS audit_events_conversation_idx ON audit_events (conversation_id, created_at);
CREATE INDEX IF NOT EXISTS audit_events_run_idx ON audit_events (run_id, created_at);
