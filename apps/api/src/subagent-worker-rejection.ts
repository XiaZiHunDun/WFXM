/**
 * D75 T1 (CQ-002): extract audit-write path for capability-rejected
 * outbox messages from handleOutboxMessage.
 *
 * When a `Delegate` message carries a capability not on the
 * `ALLOWED_CAPABILITIES` allowlist, the worker rejects before
 * invoking the LLM and writes a `rejection` audit row. The shape is
 * stable across the worker; extracted here so handleOutboxMessage
 * doesn't carry the audit-write boilerplate.
 */
import type { OutboxMessage } from "@butler/persistence/outbox.js"
import type { RuntimeStore } from "@butler/domain/runtime.js"
import { writeSubagentAudit } from "./audit-service.js"
import type { SubagentWorkerLogger } from "./subagent-worker.js"

/**
 * Audit-write helper for capability rejection. Caller passes the
 * already-parsed payload + the offending capability; the helper
 * formats the rejection reason + writes the audit row.
 */
export function writeChildRunRejection(args: {
  readonly runtimeStore: RuntimeStore | undefined
  readonly msg: OutboxMessage
  readonly childConversationId: string
  readonly role: string
  readonly task: string
  readonly capabilities: readonly string[]
  readonly invalidCapability: string
  readonly allowedCapabilities: readonly string[]
  readonly logger: SubagentWorkerLogger
}): void {
  const reason = `invalid capability: ${args.invalidCapability} (allowed: ${args.allowedCapabilities.join(", ")})`
  args.logger.warn(`[subagent-worker] rejecting outbox msg ${args.msg.messageId}: ${reason}`)
  writeSubagentAudit(args.runtimeStore, {
    ts: new Date().toISOString(),
    kind: "rejection",
    parentConversationId: args.msg.streamId,
    childConversationId: args.childConversationId,
    role: args.role,
    task: args.task,
    capabilities: args.capabilities,
    reason,
  })
}
