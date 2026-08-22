import type { RuntimeStore } from "@butler/domain/runtime.js"
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
  /** When set with runtimeStore, creates a relational Child Run (A5). */
  readonly parentRunId?: string
  readonly runtimeStore?: RuntimeStore
  readonly subject?: string
}

export interface DelegateOutcome {
  readonly role: string
  readonly capabilities: readonly Capability[]
  readonly parentConversationId: string
  readonly childConversationId: string
  /** Relational child Run id when parentRunId + runtimeStore were provided. */
  readonly childRunId: string | null
}

/**
 * Delegate a task to a child agent with a strict capability filter.
 * Writes a ChildRunCreated domain event and an outbox message atomically via
 * the bridge. When `parentRunId` + `runtimeStore` are provided, also creates
 * a queued Child Run (`parentRunId` set) and an initial model Step.
 * The actual child execution is handled asynchronously by the worker.
 *
 * Throws Error if capabilities is empty (programmer error).
 */
export async function delegate(input: DelegateInput): Promise<DelegateOutcome> {
  if (input.capabilities.length === 0) {
    throw new Error("delegate: capabilities must not be empty")
  }
  const childConversationId = `child-${input.parentConversationId}-${Date.now()}`
  const subject = input.subject ?? input.actor.id
  let childRunId: string | null = null

  if (input.runtimeStore && input.parentRunId) {
    const now = new Date()
    const store = input.runtimeStore
    await store.createConversationWithUserMessage({
      conversationId: childConversationId,
      messageId: crypto.randomUUID(),
      subject,
      content: { text: input.task },
      triggerSource: "parent_run",
      idempotencyKey: `delegate-msg:${input.parentRunId}:${childConversationId}`,
      createdAt: now,
    })
    const childRun = await store.createRun({
      id: crypto.randomUUID(),
      conversationId: childConversationId,
      parentRunId: input.parentRunId,
      triggerSource: "parent_run",
      idempotencyKey: `child-run:${input.parentRunId}:${childConversationId}`,
      subject,
      goal: input.task.slice(0, 200),
      budget: {
        maxSteps: 3,
        role: input.role,
        parentRunId: input.parentRunId,
      },
      deadline: null,
      createdAt: now,
    })
    childRunId = childRun.id
    await store.createStep({
      id: crypto.randomUUID(),
      runId: childRun.id,
      kind: "model",
      status: "queued",
      input: {
        role: input.role,
        task: input.task,
        capabilities: input.capabilities.map((c) => c.tool as string),
      },
      createdAt: now,
    })
    await store.appendAuditEvent({
      auditId: crypto.randomUUID(),
      runId: childRun.id,
      conversationId: childConversationId,
      action: "run.child_created",
      subject,
      detail: {
        parentRunId: input.parentRunId,
        parentConversationId: input.parentConversationId,
        role: input.role,
      },
      createdAt: now,
    })
  }

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
      ...(childRunId ? { childRunId } : {}),
      ...(input.parentRunId ? { parentRunId: input.parentRunId } : {}),
    },
    outbox: {
      aggregateType: "Delegate",
      payload: {
        childConversationId,
        role: input.role,
        task: input.task,
        capabilities: input.capabilities,
        ...(childRunId ? { childRunId } : {}),
        ...(input.parentRunId ? { parentRunId: input.parentRunId } : {}),
      },
    },
  })
  return {
    role: input.role,
    capabilities: input.capabilities,
    parentConversationId: input.parentConversationId,
    childConversationId,
    childRunId,
  }
}
