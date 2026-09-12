import type { RuntimeStore } from "@butler/domain/runtime.js"
import { appendAudit, type AuditEntry } from "./audit-log.js"

/**
 * Dual-write subagent audit rows to JSONL (legacy) and audit_events when a
 * runtime store is available.
 */
export function writeSubagentAudit(store: RuntimeStore | undefined, entry: AuditEntry): void {
  appendAudit(entry)
  if (!store) return
  void store
    .appendAuditEvent({
      auditId: crypto.randomUUID(),
      runId: null,
      conversationId: entry.parentConversationId,
      action: `subagent.${entry.kind}`,
      // D58 T1 (audit #3 F-01): prefer the owner who delegated over the
      // subagent role. Falls back to role for legacy callers / CLI paths
      // where no owner subject is known.
      subject: entry.ownerSubject ?? entry.role,
      detail: {
        childConversationId: entry.childConversationId,
        task: entry.task,
        capabilities: entry.capabilities,
        ...(entry.replyExcerpt ? { replyExcerpt: entry.replyExcerpt } : {}),
        ...(entry.reason ? { reason: entry.reason } : {}),
        ...(entry.toolName ? { toolName: entry.toolName } : {}),
      },
      createdAt: new Date(entry.ts),
    })
    .catch((err) => {
      // D58 T1 (audit #1 F-02): audit must never break the route/worker,
      // but persistent audit-pipeline failures were completely invisible.
      // Log to stderr so a regression in the audit pipeline surfaces in
      // operator logs. Pattern is D55 SF-04 + D57 T5 reuse.
      // eslint-disable-next-line no-console -- operator log when no logger injected
      console.error("[audit-service] appendAuditEvent failed:", err)
    })
}
