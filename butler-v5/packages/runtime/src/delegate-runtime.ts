import type { EventBridge } from "./bridge.js"

/**
 * R8.x.9: closed allowlist of capability tool names that a subagent
 * may be granted. The route layer (`tools.ts`) and the worker layer
 * (`subagent-worker.ts`) both filter inbound capability sets against
 * this list so a misconfigured LLM cannot mint arbitrary tool names.
 *
 * `general` is the implicit default when the caller does not specify
 * any capabilities; the worker treats it as "the child can do general
 * language work" without any extra tool access.
 */
export const ALLOWED_CAPABILITIES = [
  "general",
  "get_current_time",
  "summarize_today",
  "recall_history",
  "read_file",
  "run_command",
] as const
export type AllowedCapability = (typeof ALLOWED_CAPABILITIES)[number]

export interface Capability {
  readonly tool: string & { readonly __brand: "ToolName" }
}

export interface DelegateInput {
  readonly role: string
  readonly task: string
  readonly capabilities: readonly Capability[]
  readonly parentConversationId: string
  readonly actor: { readonly kind: "owner" | "agent" | "system"; readonly id: string }
  readonly bridge: EventBridge
}

export interface DelegateOutcome {
  readonly role: string
  readonly capabilities: readonly Capability[]
  readonly parentConversationId: string
  readonly childConversationId: string
}

/**
 * Delegate a task to a child agent with a strict capability filter.
 * Writes a ChildRunCreated domain event and an outbox message atomically via
 * the bridge. The actual child execution is handled asynchronously by the worker
 * after polling the outbox.
 *
 * Throws Error if capabilities is empty (programmer error).
 */
export async function delegate(input: DelegateInput): Promise<DelegateOutcome> {
  if (input.capabilities.length === 0) {
    throw new Error("delegate: capabilities must not be empty")
  }
  const childConversationId = `child-${input.parentConversationId}-${Date.now()}`
  await input.bridge.appendConversationEventWithOutbox({
    streamId: input.parentConversationId,
    eventId: `evt-${Date.now()}-delegate`,
    eventType: "ChildRunCreated",
    correlationId: `corr-${Date.now()}`,
    actor: input.actor,
    event: {
      _tag: "ChildRunCreated",
      childConversationId,
      role: input.role,
      capabilities: input.capabilities,
    },
    outbox: {
      aggregateType: "Delegate",
      payload: {
        childConversationId,
        role: input.role,
        task: input.task,
        capabilities: input.capabilities,
      },
    },
  })
  return {
    role: input.role,
    capabilities: input.capabilities,
    parentConversationId: input.parentConversationId,
    childConversationId,
  }
}
