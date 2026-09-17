import type { RuntimeStore } from "@butler/domain/runtime.js"
import type { AuditEventSummary, AuditLogReader } from "./signal.js"

export interface AuditFatigueReaderOptions {
  readonly limit?: number
  /**
   * D70 T3 (audit #11 CQ-030): actor string the reader attaches to
   * emitted AuditEventSummary rows. Previously hardcoded as "owner"
   * (SEC-013 sentinel). Callers that own an authenticated ownerId
   * (e.g. POST /v1/owner/* with bearer auth, D71+ work) pass the
   * resolved id; the loopback-only owner-route surface keeps the
   * default "owner" sentinel until bearer auth lands.
   */
  readonly actor?: string
}

/**
 * D69 T1 — Shared audit-fatigue reader adapter.
 *
 * Both `wechat-inbound-butler.ts` (D68 T2a) and `owner-routes/audit-fatigue.ts`
 * (D69 T1) read from the runtime `audit_events` table to compute fatigue
 * signals. The previous owner-route path read the subagent JSONL log (D64 T3
 * bridge), which only observed subagent delegations — owner audit fatigue
 * missed every non-subagent fatigue decision. This helper unifies both
 * readers on `runtimeStore.listRecentAuditEvents` (D66 T1a) so the butler
 * loop and the owner control surface observe the same audit stream.
 *
 * Mapping `AuditEventRecord` → `AuditEventSummary`:
 * - `auditId`        → `event_id`  (UUID, unique per row)
 * - `subject`        → `tool_name` (subject column = actor; for fatigue
 *                                     decisions this is the tool name per
 *                                     D58 T1 spec)
 * - `actor`          → `"owner"`   — D69 T3 will thread real ownerId from
 *                                     session once bearer auth lands
 * - `createdAt`      → `ts`        (ms epoch)
 * - `decision`       → `"allow"`   (audit_events has no decision column;
 *                                     the fatigue reader is only invoked
 *                                     when the owner-action *would* be
 *                                     allowed otherwise; checklist/cooldown
 *                                     interventions are emitted as
 *                                     `fatigue.decision` events but the
 *                                     chokepoint still allows the action
 *                                     after the intervention)
 *
 * Closes audit findings:
 *   SO-001 owner-routes/audit-fatigue.ts reader swap (pre-scoped D68 #1)
 *   SO-002 subagentAuditAsFatigueReader + ownerAuditReader consolidation
 *   CQ-032 wechat-inbound-butler.ts hardcoded actor='owner'
 *   SO-009 wechat-inbound-butler.ts fatigue reader hardcoded actor='owner'
 *   SO-014 _wiring unused param (D63 god-fn split leftover)
 *   SO-018 ownerAuditReader process.env direct read
 *   SEC-013 currentOwnerActor() returns literal "owner" (sentinel)
 *   CQ-035 audit-fatigue.ts TODO(D65+) for session lookup
 */
export function auditFatigueReader(
  runtimeStore: RuntimeStore,
  options: AuditFatigueReaderOptions = {},
): AuditLogReader {
  const limit = options.limit ?? 100
  const actor = options.actor ?? "owner" // D70 T3: caller-provided actor, default sentinel
  return {
    readRecent: async (windowMs: number): Promise<readonly AuditEventSummary[]> => {
      const events = await runtimeStore.listRecentAuditEvents({ windowMs, limit })
      return events.map((e): AuditEventSummary => ({
        event_id: e.auditId,
        tool_name: e.subject,
        actor,
        ts: e.createdAt.getTime(),
        decision: "allow" as const,
      }))
    },
  }
}