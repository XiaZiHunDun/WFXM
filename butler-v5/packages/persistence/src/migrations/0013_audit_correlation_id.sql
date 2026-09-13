-- D63 T3 (audit #9 F-04): add correlation_id column to audit_events.
-- The event_store requires correlationId per-event (domain/event-sourcing.ts:96),
-- but the audit_events table was missing the column. Owner queries cannot
-- link audit rows to inbound request messageId, especially for stubReply /
-- early-return paths that bypass LLM run creation.
--
-- Threading correlationId from route handlers → runtime → appendAuditEvent
-- is part of the T3 ship; future cycles can complete the coverage across
-- the remaining ~15 emit sites.

ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS correlation_id text;
CREATE INDEX IF NOT EXISTS audit_events_correlation_idx
  ON audit_events (correlation_id, created_at);