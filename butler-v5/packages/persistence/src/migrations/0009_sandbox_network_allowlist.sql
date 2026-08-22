-- P2b: per-host sandbox egress allowlist on ScopedGrant (Grant-bound, not global env)
ALTER TABLE scoped_grants
  ADD COLUMN IF NOT EXISTS network_allowlist jsonb;
