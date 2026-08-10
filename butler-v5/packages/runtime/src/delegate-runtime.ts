import type { EventBridge } from "./bridge.js"

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
 * Writes a ChildRunCreated domain event + an outbox message for the worker
 * layer. The actual child execution is handled asynchronously by the worker
 * after polling the outbox.
 *
 * Throws Error if capabilities is empty (programmer error).
 */
export async function delegate(input: DelegateInput): Promise<DelegateOutcome> {
  if (input.capabilities.length === 0) {
    throw new Error("delegate: capabilities must not be empty")
  }
  const childConversationId = `child-${input.parentConversationId}-${Date.now()}`
  await input.bridge.appendConversationEvent({
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
  })
  await input.bridge.enqueueOutbox({
    streamId: input.parentConversationId,
    aggregateType: "Delegate",
    payload: {
      childConversationId,
      role: input.role,
      task: input.task,
      capabilities: input.capabilities,
    },
  })
  return {
    role: input.role,
    capabilities: input.capabilities,
    parentConversationId: input.parentConversationId,
    childConversationId,
  }
}
