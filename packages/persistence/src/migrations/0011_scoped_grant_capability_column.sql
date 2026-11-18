-- D2.2: Lift capability from scope JSON to first-class column on scoped_grants.
-- DESIGN §10.3 lists capability as a first-class ScopedGrant field (alongside subject/scope).
-- Production always writes a single capability (buildScopedGrantScopeFromPending caps it
-- to [input.capability]); backfill extracts index 0 from the existing array.
-- Column stays nullable during rollout; concurrent inserts continue to land in scope JSON.
-- The runtime read path (D2.2 step 2) prefers column and falls back to scope->'capabilities'->0.

ALTER TABLE scoped_grants
  ADD COLUMN IF NOT EXISTS capability text;

-- Backfill from existing rows. Idempotent: preserves already-populated column on re-run.
UPDATE scoped_grants
SET capability = scope->'capabilities'->>0
WHERE capability IS NULL
  AND jsonb_typeof(scope->'capabilities') = 'array'
  AND jsonb_array_length(scope->'capabilities') >= 1;

-- Index supports capability-only filters (revokeScopedGrantsForCapability + MCP grant lifecycles).
CREATE INDEX IF NOT EXISTS scoped_grants_capability_idx
  ON scoped_grants (capability)
  WHERE capability IS NOT NULL;
