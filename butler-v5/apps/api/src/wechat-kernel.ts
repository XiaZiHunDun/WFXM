/**
 * Local mirror of the minimal runtime surface needed by the wechat
 * butler loop (R8.x.3): `AgentKernel` + `decodeDecision` +
 * `ModelDecision`.
 *
 * The runtime package owns the canonical `packages/runtime/src/agent-kernel.ts`
 * and `packages/runtime/src/decision.ts`. The runtime `index.ts`
 * re-exports only `bridge.js`, and the package `exports` map does not
 * expose `./agent-kernel.js` or `./decision.js`. Adding those exports
 * is a cross-cutting change outside this task's allowed path scope,
 * so we mirror the shape here. The runtime version remains the source
 * of truth — these copies must track any runtime changes exactly.
 */

import type { EventBridge } from "@butler/runtime/bridge.js"

// ---------- agent-kernel mirror ----------

export type KernelState =
  | "idle"
  | "running"
  | "responded"
  | "tooling"
  | "delegating"
  | "waiting_approval"
  | "completed"
  | "failed"

export interface AgentKernelConfig {
  readonly bridge: EventBridge
  readonly conversationId: string
  readonly projectId: string
  readonly actor: { readonly kind: "owner" | "agent" | "system"; readonly id: string }
}

export class AgentKernel {
  state: KernelState = "idle"
  private turnCounter = 0

  constructor(private readonly config: AgentKernelConfig) {}

  private nextTurnId(): string {
    this.turnCounter += 1
    return `evt-${Date.now()}-turn-${this.turnCounter}`
  }

  async openTurn(input: {
    userMessage: { role: "user" | "assistant" | "system" | "tool"; content: string }
  }): Promise<void> {
    if (this.state === "completed" || this.state === "failed") {
      return Promise.reject(new Error(`cannot openTurn on ${this.state} conversation`))
    }
    this.state = "running"
    await this.config.bridge.appendConversationEvent({
      streamId: this.config.conversationId,
      eventId: this.nextTurnId(),
      eventType: "TurnOpened",
      correlationId: `corr-${Date.now()}`,
      actor: this.config.actor,
      event: {
        _tag: "TurnOpened",
        role: input.userMessage.role,
        content: input.userMessage.content,
      },
    })
  }

  async applyDecision(decision: ModelDecision): Promise<void> {
    if (this.state === "completed" || this.state === "failed") {
      return Promise.reject(new Error(`cannot applyDecision on ${this.state} conversation`))
    }
    switch (decision._tag) {
      case "Respond":
        await this.config.bridge.appendConversationEvent({
          streamId: this.config.conversationId,
          eventId: `evt-${Date.now()}-resp`,
          eventType: "AssistantMessageProduced",
          correlationId: `corr-${Date.now()}`,
          actor: this.config.actor,
          event: { _tag: "AssistantMessageProduced", content: decision.content },
        })
        this.state = "completed"
        return
      case "CallTool":
        this.state = "tooling"
        return
      case "Delegate":
        this.state = "delegating"
        return
      case "AskApproval":
        this.state = "waiting_approval"
        return
      case "Finish":
        this.state = "completed"
        return
      default: {
        const _: never = decision
        void _
        return
      }
    }
  }
}

// ---------- decision mirror ----------

export type ModelDecision =
  | { readonly _tag: "Respond"; readonly content: string }
  | { readonly _tag: "CallTool"; readonly toolName: string; readonly args: Record<string, unknown> }
  | { readonly _tag: "Delegate"; readonly role: string; readonly task: string }
  | { readonly _tag: "AskApproval"; readonly question: string }
  | { readonly _tag: "Finish"; readonly reason: string }

export type DecodeResult =
  | { readonly ok: true; readonly value: ModelDecision }
  | { readonly ok: false; readonly reason: string }

export function decodeDecision(raw: string): DecodeResult {
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return { ok: false, reason: "invalid JSON" }
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return { ok: false, reason: "not an object" }
  }
  const obj = parsed as Record<string, unknown>
  const tag = obj["_tag"]
  switch (tag) {
    case "Respond": {
      const content = obj["content"]
      if (typeof content !== "string")
        return { ok: false, reason: "Respond.content must be string" }
      return { ok: true, value: { _tag: "Respond", content } }
    }
    case "CallTool": {
      const toolName = obj["toolName"]
      const args = obj["args"]
      if (typeof toolName !== "string")
        return { ok: false, reason: "CallTool.toolName must be string" }
      if (!args || typeof args !== "object" || Array.isArray(args)) {
        return { ok: false, reason: "CallTool.args must be object" }
      }
      return {
        ok: true,
        value: { _tag: "CallTool", toolName, args: args as Record<string, unknown> },
      }
    }
    case "Delegate": {
      const role = obj["role"]
      const task = obj["task"]
      if (typeof role !== "string") return { ok: false, reason: "Delegate.role must be string" }
      if (typeof task !== "string") return { ok: false, reason: "Delegate.task must be string" }
      return { ok: true, value: { _tag: "Delegate", role, task } }
    }
    case "AskApproval": {
      const question = obj["question"]
      if (typeof question !== "string")
        return { ok: false, reason: "AskApproval.question must be string" }
      return { ok: true, value: { _tag: "AskApproval", question } }
    }
    case "Finish": {
      const reason = obj["reason"]
      if (typeof reason !== "string") return { ok: false, reason: "Finish.reason must be string" }
      return { ok: true, value: { _tag: "Finish", reason } }
    }
    default:
      return { ok: false, reason: `unknown tag: ${String(tag)}` }
  }
}
