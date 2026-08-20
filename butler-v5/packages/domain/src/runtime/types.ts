// ─── Runtime identifiers ─────────────────────────────────
export type ConversationId = string
export type MessageId = string
export type RunId = string
export type StepId = string

// ─── Trigger ─────────────────────────────────────────────
export type TriggerSource = "channel" | "cli" | "api" | "webhook" | "schedule" | "parent_run"
export type TrustLevel = "untrusted" | "trusted" | "owner"

export interface RunTrigger {
  readonly subject: string
  readonly source: TriggerSource
  readonly conversationRef: string | null
  readonly payload: Readonly<Record<string, unknown>>
  readonly trustLevel: TrustLevel
  readonly idempotencyKey: string
}

// ─── Core runtime entities ───────────────────────────────
export interface Conversation {
  readonly id: ConversationId
  readonly subject: string
  readonly createdAt: number
  readonly updatedAt: number
}

export type MessageRole = "user" | "assistant" | "system" | "tool"

export interface Message {
  readonly id: MessageId
  readonly conversationId: ConversationId
  readonly role: MessageRole
  readonly content: Readonly<Record<string, unknown>>
  readonly triggerSource: TriggerSource | null
  readonly idempotencyKey: string | null
  readonly createdAt: number
}

export type RunStatus =
  | "queued"
  | "running"
  | "waiting_approval"
  | "waiting_external"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "expired"

export interface RunBudget {
  readonly maxSteps: number
}

export interface Run {
  readonly id: RunId
  readonly conversationId: ConversationId
  readonly parentRunId: RunId | null
  readonly trigger: RunTrigger
  readonly goal: string
  readonly budget: RunBudget
  readonly deadline: number | null
  readonly status: RunStatus
  readonly version: number
  readonly createdAt: number
  readonly updatedAt: number
}

export type StepKind = "model" | "capability" | "approval" | "result"
export type StepStatus = "queued" | "running" | "waiting" | "succeeded" | "failed"

export interface Step {
  readonly id: StepId
  readonly runId: RunId
  readonly kind: StepKind
  readonly status: StepStatus
  readonly input: Readonly<Record<string, unknown>>
  readonly output: Readonly<Record<string, unknown>> | null
  readonly createdAt: number
  readonly updatedAt: number
}
