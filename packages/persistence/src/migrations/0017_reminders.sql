-- Phase 2 C1: owner reminders (personal scheduled text pushes).
-- Rows are created from chat via the create_reminder tool and consumed by
-- the opt-in reminder worker. Reminders never trigger tools or side effects.
CREATE TABLE IF NOT EXISTS reminders (
  reminder_id uuid PRIMARY KEY NOT NULL,
  subject text NOT NULL,
  wechat_user_id text NOT NULL,
  conversation_id text NOT NULL,
  content text NOT NULL,
  fire_at timestamptz NOT NULL,
  repeat text NOT NULL,
  status text NOT NULL,
  attempt_count integer NOT NULL DEFAULT 0,
  last_attempt_at timestamptz,
  last_error text,
  fired_at timestamptz,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS reminders_status_fire_idx
  ON reminders (status, fire_at);

CREATE INDEX IF NOT EXISTS reminders_subject_status_idx
  ON reminders (subject, status, fire_at);
