/**
 * D75 T1 (CQ-002): extract payload parsing from handleOutboxMessage.
 *
 * handleOutboxMessage was 273 lines. The first ~25 lines are pure
 * payload-shape coercion (no I/O, no side effects) — extracted here
 * so the orchestrator focuses on the policy + side-effect surface.
 */
import type { OutboxMessage } from "@butler/persistence/outbox.js"
import { normalizeCapabilityNames } from "./capability-guard.js"

/**
 * Parsed shape of a `Delegate` outbox message payload. All fields are
 * coerced to safe defaults — empty strings / null — so downstream code
 * can rely on the type without re-checking each access.
 */
export interface ParsedDelegatePayload {
  readonly childConversationId: string
  readonly role: string
  readonly task: string
  readonly capabilities: readonly string[]
  readonly childRunId: string | null
  readonly notifySubject: string
}

/**
 * Coerce an outbox message's payload into a typed shape. Unknown /
 * missing fields default to empty strings or `null`; the caller's
 * downstream code is responsible for rejecting empty `task` /
 * `childConversationId`.
 */
export function parseDelegateOutboxPayload(msg: OutboxMessage): ParsedDelegatePayload {
  const payload = msg.payload as {
    childConversationId?: unknown
    role?: unknown
    task?: unknown
    capabilities?: unknown
    childRunId?: unknown
    parentRunId?: unknown
    notifySubject?: unknown
  }
  return {
    childConversationId:
      typeof payload.childConversationId === "string" ? payload.childConversationId : "",
    role: typeof payload.role === "string" && payload.role.trim() ? payload.role : "general",
    task: typeof payload.task === "string" ? payload.task : "",
    capabilities: normalizeCapabilityNames(payload.capabilities),
    childRunId: typeof payload.childRunId === "string" ? payload.childRunId : null,
    notifySubject:
      typeof payload.notifySubject === "string" ? payload.notifySubject.trim() : "",
  }
}
