-- Project Knowledge (DESIGN §9 layer 3). Project-scoped ingest + substring recall; not embedding.
CREATE TABLE IF NOT EXISTS project_knowledge_items (
  item_id uuid PRIMARY KEY NOT NULL,
  project_id text NOT NULL,
  title text NOT NULL,
  kind text NOT NULL,
  body text NOT NULL,
  byte_size integer NOT NULL,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS project_knowledge_items_project_updated_idx
  ON project_knowledge_items (project_id, updated_at DESC);
