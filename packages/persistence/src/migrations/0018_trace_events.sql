-- Phase 5 P0: durable local trace events (dual-write from LocalTracer).
-- No foreign keys: traces must remain after Run / conversation cleanup and
-- writes must not depend on insert ordering. Retention is enforced by
-- TraceStore.prune (age + max rows).
CREATE TABLE IF NOT EXISTS trace_events (
  id uuid PRIMARY KEY NOT NULL,
  kind text NOT NULL,
  name text NOT NULL,
  status text NOT NULL,
  turn_id text,
  conversation_id text,
  run_id text,
  step_id text,
  parent_run_id text,
  subject text,
  trigger_source text,
  capability text,
  policy_decision text,
  grant_id text,
  waiting_step_id text,
  duration_ms integer,
  token_input integer,
  token_output integer,
  token_total integer,
  cost_usd double precision,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS trace_events_created_idx
  ON trace_events (created_at);

CREATE INDEX IF NOT EXISTS trace_events_run_idx
  ON trace_events (run_id, created_at);

CREATE INDEX IF NOT EXISTS trace_events_conversation_idx
  ON trace_events (conversation_id, created_at);

CREATE INDEX IF NOT EXISTS trace_events_turn_idx
  ON trace_events (turn_id, created_at);

CREATE INDEX IF NOT EXISTS trace_events_kind_idx
  ON trace_events (kind, created_at);
