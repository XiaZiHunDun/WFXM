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
      subject: entry.role,
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
    .catch(() => {
      // audit must never break the route or worker
    })
}
