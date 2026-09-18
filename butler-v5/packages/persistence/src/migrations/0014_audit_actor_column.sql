-- D71 T1 (audit #12 CQ-009 / SO-001): add actor column to audit_events.
-- Pre-D71 the audit_events.subject column overloaded two meanings: tool
-- name (for fatigue decisions like "write_file") AND owner identity (for
-- owner-route actions like "owner.replay" where subject was set to literal
-- "owner"). The auditFatigueReader was forced to hardcode actor='owner'
-- because there was no schema-level actor column.
--
-- This migration adds a nullable actor column. Existing rows backfill to
-- 'owner' (the documented sentinel); new emit sites can thread a real
-- actor without touching subject. The runtimeStore and memory store
-- accept an optional `actor` field on appendAuditEvent; absent → 'owner'
-- (preserves D70 T3 default).
--
-- Future cycles (D71+): thread actor through the remaining 10+ emit
-- sites that currently hardcode subject='owner'. CQ-009 / SO-001 first
-- closure; SO-001 carry-forward deferred for full coverage.

ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS actor text;
UPDATE audit_events SET actor = 'owner' WHERE actor IS NULL;
ALTER TABLE audit_events ALTER COLUMN actor SET NOT NULL;
CREATE INDEX IF NOT EXISTS audit_events_actor_idx
  ON audit_events (actor, created_at);
