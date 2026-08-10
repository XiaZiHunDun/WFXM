import type { EventBridge } from "./bridge.js"
import type { ModelDecision } from "./decision.js"

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
      throw new Error(`cannot openTurn on ${this.state} conversation`)
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
      throw new Error(`cannot applyDecision on ${this.state} conversation`)
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
