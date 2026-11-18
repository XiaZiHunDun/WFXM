-- Named document ingest (P4). Stores extracted text + provenance; not a RAG index.
CREATE TABLE IF NOT EXISTS documents (
  document_id uuid PRIMARY KEY NOT NULL,
  subject text NOT NULL,
  title text NOT NULL,
  format text NOT NULL,
  mime_type text NOT NULL,
  byte_size integer NOT NULL,
  extracted_text text NOT NULL,
  status text NOT NULL,
  failure_reason text,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS documents_subject_updated_idx
  ON documents (subject, updated_at DESC);
