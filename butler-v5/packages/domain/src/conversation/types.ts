// domain/conversation/types.ts
// 对话域 ADT — 状态机、消息、事件、上下文窗口

import type { LoopError } from "../errors.js"
import type { IntentReceipt } from "../guards/index.js"

// ─── 品牌类型 ───────────────────────────────────────────
export type ConversationId = string & { readonly __brand: "ConversationId" }
export type LoopId = string & { readonly __brand: "LoopId" }
export type ProjectIdRef = string & { readonly __brand: "ProjectIdRef" }
export type TurnId = string & { readonly __brand: "TurnId" }
export type ToolCallId = string & { readonly __brand: "ToolCallId" }

// ─── 对话/回合状态 ──────────────────────────────────────
export type ConversationStatus = "open" | "running" | "waiting" | "completed"
export type TurnStatus = "running" | "responded" | "tooled" | "completed" | "failed"

// ─── 消息 ───────────────────────────────────────────────
export type MessageRole = "user" | "assistant" | "tool" | "system"

export type Message = {
  readonly id: string
  readonly conversationId: ConversationId
  readonly role: MessageRole
  readonly content: string
  readonly toolCalls?: readonly ToolCallPayload[]
  readonly toolCallId?: string
  readonly createdAt: number
}

export type ToolCallPayload = {
  readonly id: string
  readonly name: string
  readonly input: Record<string, unknown>
}

// ─── 对话聚合（含 Turn 列表） ──────────────────────────
export interface Turn {
  readonly id: TurnId
  readonly status: TurnStatus
  readonly userMessage: Message | null
  readonly assistantMessage: Message | null
  readonly toolCallId: ToolCallId | null
  readonly toolOutput: string | null
}

export interface Conversation {
  readonly id: ConversationId
  readonly projectId: ProjectIdRef
  readonly status: ConversationStatus
  readonly turns: readonly Turn[]
}

// ─── 对话状态机 ─────────────────────────────────────────
export type ConversationState =
  | { readonly _tag: "Idle" }
  | { readonly _tag: "Running"; readonly loopId: LoopId }
  | { readonly _tag: "AwaitingToolResult"; readonly toolCallId: string; readonly loopId: LoopId }
  | { readonly _tag: "AwaitingOwnerInput"; readonly prompt: string; readonly since: number }
  | { readonly _tag: "AwaitingReview"; readonly receiptId: string; readonly reviewerAgent: string }
  | { readonly _tag: "Completed"; readonly receipt?: IntentReceipt }
  | { readonly _tag: "Failed"; readonly error: LoopError; readonly receipt?: IntentReceipt }

// ─── 对话事件 ───────────────────────────────────────────
export type ConversationEvent =
  | { readonly _tag: "ConversationStarted"; readonly conversationId: ConversationId }
  | { readonly _tag: "MessageAdded"; readonly message: Message }
  | { readonly _tag: "ToolCallStarted"; readonly toolCallId: string }
  | { readonly _tag: "ToolCallCompleted"; readonly toolCallId: string; readonly result: unknown }
  | { readonly _tag: "OwnerInputReceived"; readonly loopId: LoopId }
  | { readonly _tag: "OwnerInputTimeout" }
  | { readonly _tag: "ReviewRequested"; readonly receiptId: string; readonly reviewerAgent: string }
  | { readonly _tag: "ReviewCompleted"; readonly receiptId: string; readonly approved: boolean }
  | { readonly _tag: "ConversationCompleted"; readonly receipt?: IntentReceipt }
  | {
      readonly _tag: "ConversationFailed"
      readonly error: LoopError
      readonly receipt?: IntentReceipt
    }

// ─── Agent 角色 ─────────────────────────────────────────
export type AgentPersona = {
  readonly role: "Coder" | "Reviewer" | "Arbiter"
  readonly name: string
  readonly systemPrompt: string
  readonly model: string
}

// ─── 上下文窗口 ─────────────────────────────────────────
export type ContextWindow = {
  readonly tokens: number
  readonly maxTokens: number
  readonly compressed: boolean
  readonly summary?: string
}

// ─── 上下文图节点 ───────────────────────────────────────
export type ContextNode = {
  readonly id: string
  readonly type: "message" | "tool_call" | "tool_result" | "summary"
  readonly refs: readonly string[]
}
