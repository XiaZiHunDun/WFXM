-- D42 §12 G4 candidate auto-promote (5 column + 1 partial index).
-- DESIGN §12 G4 — sweeper promotes candidate (age >= 3d) to status='confirmed'
-- and tags with promoted_by='sweeper'; owner can rollback within 7d window
-- (sets rolled_back_by/at/reason, status returns to 'candidate').
-- Append-only migration: 5 column ADD + 1 partial index; no column drop/rename.

ALTER TABLE durable_memories
  ADD COLUMN IF NOT EXISTS promoted_by TEXT,           -- 'owner' | 'sweeper' | NULL
  ADD COLUMN IF NOT EXISTS promoted_at TIMESTAMPTZ,    -- sweeper promote time, NULL for owner-confirmed
  ADD COLUMN IF NOT EXISTS rolled_back_by TEXT,        -- owner who rolled back (NULL if never)
  ADD COLUMN IF NOT EXISTS rolled_back_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS rollback_reason TEXT;

-- Partial index supports sweeper scan: WHERE status='candidate' ORDER BY created_at.
-- Composite (status, created_at) keeps index narrow; partial WHERE keeps it small.
CREATE INDEX IF NOT EXISTS durable_memories_auto_promote_sweep_idx
  ON durable_memories (created_at)
  WHERE status = 'candidate';