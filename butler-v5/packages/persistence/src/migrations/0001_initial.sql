-- 与 schema.ts 同步；由 Drizzle migrator 或手工 psql 应用。
CREATE TABLE IF NOT EXISTS event_store (
  event_id uuid PRIMARY KEY NOT NULL,
  stream_id text NOT NULL,
  stream_type text NOT NULL,
  stream_version integer NOT NULL,
  event_type text NOT NULL,
  event_version integer NOT NULL,
  payload jsonb NOT NULL,
  occurred_at timestamptz NOT NULL,
  causation_id text,
  correlation_id text NOT NULL,
  actor_kind text NOT NULL,
  actor_id text NOT NULL
);
CREATE INDEX IF NOT EXISTS event_store_stream_idx ON event_store (stream_id, stream_version);
CREATE UNIQUE INDEX IF NOT EXISTS event_store_stream_uniq ON event_store (stream_id, stream_version);

CREATE TABLE IF NOT EXISTS outbox (
  message_id uuid PRIMARY KEY NOT NULL,
  stream_id text NOT NULL,
  aggregate_type text NOT NULL,
  payload jsonb NOT NULL,
  status text NOT NULL,
  attempt_count integer NOT NULL DEFAULT 0,
  next_attempt_at timestamptz NOT NULL,
  lease_owner text,
  lease_until timestamptz,
  last_error text,
  created_at timestamptz NOT NULL,
  delivered_at timestamptz
);
CREATE INDEX IF NOT EXISTS outbox_status_idx ON outbox (status, next_attempt_at);
CREATE INDEX IF NOT EXISTS outbox_lease_idx ON outbox (lease_until);

CREATE TABLE IF NOT EXISTS snapshots (
  stream_id text PRIMARY KEY NOT NULL,
  stream_version integer NOT NULL,
  payload jsonb NOT NULL,
  taken_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS projections (
  projection_name text PRIMARY KEY NOT NULL,
  version integer NOT NULL,
  state jsonb NOT NULL,
  updated_at timestamptz NOT NULL
);