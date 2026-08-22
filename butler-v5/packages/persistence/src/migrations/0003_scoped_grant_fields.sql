-- A3: ScopedGrant fields aligned with DESIGN §7.3
-- capability remains in scope JSON; first-class columns for approval linkage and sandbox.
ALTER TABLE scoped_grants
  ADD COLUMN IF NOT EXISTS delegable boolean NOT NULL DEFAULT false;

ALTER TABLE scoped_grants
  ADD COLUMN IF NOT EXISTS approval_id uuid;

ALTER TABLE scoped_grants
  ADD COLUMN IF NOT EXISTS sandbox_profile text;

CREATE INDEX IF NOT EXISTS scoped_grants_approval_idx
  ON scoped_grants (approval_id)
  WHERE approval_id IS NOT NULL;
