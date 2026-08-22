-- Task / Procedure baseline. No DAG; Procedure has no independent run state.
CREATE TABLE IF NOT EXISTS procedures (
  procedure_id uuid PRIMARY KEY NOT NULL,
  name text NOT NULL,
  version integer NOT NULL,
  steps jsonb NOT NULL,
  created_at timestamptz NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS procedures_name_version_uniq
  ON procedures (name, version);

CREATE TABLE IF NOT EXISTS tasks (
  task_id uuid PRIMARY KEY NOT NULL,
  subject text NOT NULL,
  title text NOT NULL,
  goal text NOT NULL,
  status text NOT NULL,
  conversation_id text,
  procedure_id uuid,
  procedure_step_index integer,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS tasks_subject_status_idx
  ON tasks (subject, status, updated_at DESC);
