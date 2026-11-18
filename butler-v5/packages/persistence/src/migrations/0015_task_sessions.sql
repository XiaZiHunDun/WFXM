-- P4.1: durable pi task-layer sessions.
-- The task layer rebuilds an Agent from this snapshot on every turn; the
-- pending_step column anchors a paused approval so resume can finish it.
CREATE TABLE IF NOT EXISTS task_sessions (
  task_id text PRIMARY KEY NOT NULL,
  project_id text NOT NULL,
  cwd text NOT NULL,
  status text NOT NULL,
  snapshot jsonb NOT NULL,
  pending_step jsonb,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS task_sessions_status_updated_idx
  ON task_sessions (status, updated_at DESC);
