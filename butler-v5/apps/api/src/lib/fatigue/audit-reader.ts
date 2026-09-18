import type { RuntimeStore } from "@butler/domain/runtime.js"
import type { AuditEventSummary, AuditLogReader } from "./signal.js"

export interface AuditFatigueReaderOptions {
  readonly limit?: number
  /**
   * D71 T1 (audit #12 CQ-009): when set, filters the underlying
   * listRecentAuditEvents query to only rows where actor column equals
   * this string. Backed by the audit_events.actor column (migration 0014).
   * Pre-D71 this was an in-memory override only; now the filter rides
   * on the SQL query so the actor index is used.
   */
  readonly actor?: string
  /**
   * D71 T1 (audit #12 CQ-009): when true (default false), use the
   * per-row actor column from the AuditEventRecord when mapping to
   * AuditEventSummary. Pre-D71 the summary's actor was hardcoded to
   * 'owner'. With columnActor=true each summary carries its own
   * actor; otherwise the reader falls back to options.actor or the
   * 'owner' sentinel for backward compatibility with call sites that
   * don't yet thread actor.
   */
  readonly columnActor?: boolean
}

/**
 * D69 T1 — Shared audit-fatigue reader adapter (D71 T1: actor column wiring).
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
 * - `subject`        → `tool_name` (subject column holds the tool name per
 *                                     D58 T1 spec; for owner actions it
 *                                     carries the action key like 'owner.replay')
 * - `actor`          → `e.actor`  (D71 T1: per-row column; falls back to
 *                                     options.actor or 'owner' sentinel when
 *                                     columnActor=false for backward compat)
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
 *   CQ-009 audit_events.subject overloaded for tool name + owner identity
 *   SO-001 dedicated actor column (D68 pre-scoped #5; D71 first-class)
 */
export function auditFatigueReader(
  runtimeStore: RuntimeStore,
  options: AuditFatigueReaderOptions = {},
): AuditLogReader {
  const limit = options.limit ?? 100
  const actorFilter = options.actor
  const useColumnActor = options.columnActor ?? false
  return {
    readRecent: async (windowMs: number): Promise<readonly AuditEventSummary[]> => {
      const events = await runtimeStore.listRecentAuditEvents({
        ...(actorFilter !== undefined ? { actor: actorFilter } : {}),
        windowMs,
        limit,
      })
      return events.map((e): AuditEventSummary => ({
        event_id: e.auditId,
        tool_name: e.subject,
        // D71 T1: per-row actor when columnActor is enabled (D71+
        // migration); otherwise fall back to options.actor or 'owner'
        // sentinel (D70 T3 behavior) for call sites that haven't yet
        // been wired to thread actor.
        actor: useColumnActor ? e.actor : (options.actor ?? "owner"),
        ts: e.createdAt.getTime(),
        decision: "allow" as const,
      }))
    },
  }
}