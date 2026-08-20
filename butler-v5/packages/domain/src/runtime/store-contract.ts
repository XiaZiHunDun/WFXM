import type { ScopedGrantRecord } from "../governance/types.js"
import type { RunStatus, StepKind, StepStatus, TriggerSource } from "./types.js"

export interface StoredMessage {
  readonly id: string
  readonly conversationId: string
  readonly role: "user" | "assistant" | "system" | "tool"
  readonly content: Readonly<Record<string, unknown>>
  readonly triggerSource: TriggerSource | null
  readonly idempotencyKey: string | null
  readonly createdAt: Date
}

export interface StoredRun {
  readonly id: string
  readonly conversationId: string
  readonly parentRunId: string | null
  readonly triggerSource: TriggerSource
  readonly idempotencyKey: string
  readonly subject: string
  readonly goal: string
  readonly budget: Readonly<Record<string, unknown>>
  readonly deadline: Date | null
  readonly status: RunStatus
  readonly version: number
  readonly createdAt: Date
  readonly updatedAt: Date
}

export interface StoredStep {
  readonly id: string
  readonly runId: string
  readonly kind: StepKind
  readonly status: StepStatus
  readonly input: Readonly<Record<string, unknown>>
  readonly output: Readonly<Record<string, unknown>> | null
  readonly createdAt: Date
  readonly updatedAt: Date
}

export interface RuntimeStore {
  readonly createConversationWithUserMessage: (input: {
    readonly conversationId: string
    readonly messageId: string
    readonly subject: string
    readonly content: Readonly<Record<string, unknown>>
    readonly triggerSource: TriggerSource
    readonly idempotencyKey: string
    readonly createdAt: Date
  }) => Promise<{ readonly conversationId: string; readonly messageId: string }>
  readonly createRun: (input: {
    readonly id: string
    readonly conversationId: string
    readonly parentRunId: string | null
    readonly triggerSource: TriggerSource
    readonly idempotencyKey: string
    readonly subject: string
    readonly goal: string
    readonly budget: Readonly<Record<string, unknown>>
    readonly deadline: Date | null
    readonly createdAt: Date
  }) => Promise<StoredRun>
  readonly transitionRunStatus: (
    runId: string,
    expectedVersion: number,
    status: RunStatus,
    updatedAt: Date,
  ) => Promise<StoredRun>
  readonly createStep: (input: {
    readonly id: string
    readonly runId: string
    readonly kind: StepKind
    readonly status: StepStatus
    readonly input: Readonly<Record<string, unknown>>
    readonly createdAt: Date
  }) => Promise<StoredStep>
  readonly listMessages: (conversationId: string) => Promise<readonly StoredMessage[]>
  readonly appendMessage: (input: {
    readonly messageId: string
    readonly conversationId: string
    readonly role: StoredMessage["role"]
    readonly content: Readonly<Record<string, unknown>>
    readonly triggerSource: TriggerSource | null
    readonly idempotencyKey: string | null
    readonly createdAt: Date
  }) => Promise<StoredMessage>
  readonly getRun: (runId: string) => Promise<StoredRun | null>
  readonly getStep: (stepId: string) => Promise<StoredStep | null>
  readonly updateStep: (input: {
    readonly stepId: string
    readonly status?: StepStatus
    readonly output?: Readonly<Record<string, unknown>> | null
    readonly updatedAt: Date
  }) => Promise<StoredStep>
  readonly listWaitingApprovalSteps: () => Promise<readonly StoredStep[]>
  readonly listWaitingApprovalStepsForConversation: (
    conversationId: string,
  ) => Promise<readonly StoredStep[]>
  readonly createScopedGrant: (input: {
    readonly grantId: string
    readonly runId: string
    readonly subject: string
    readonly scope: Readonly<Record<string, unknown>>
    readonly remainingUses: number | null
    readonly expiresAt: Date
    readonly createdAt: Date
  }) => Promise<ScopedGrantRecord>
  readonly findActiveGrant: (input: {
    readonly runId: string
    readonly subject: string
    readonly capability: string
    readonly now: Date
  }) => Promise<ScopedGrantRecord | null>
  readonly appendAuditEvent: (input: {
    readonly auditId: string
    readonly runId: string | null
    readonly conversationId: string | null
    readonly action: string
    readonly subject: string
    readonly detail: Readonly<Record<string, unknown>>
    readonly createdAt: Date
  }) => Promise<void>
  readonly updateScopedGrantRemainingUses: (
    grantId: string,
    remainingUses: number | null,
  ) => Promise<void>
}

export type ReadModelSource = "event_store" | "hybrid" | "relational"

export function resolveReadModelSource(
  env: Readonly<Record<string, string | undefined>>,
): ReadModelSource {
  const raw = (env["BUTLER_V5_READ_MODEL"] ?? "event_store").trim().toLowerCase()
  if (raw === "hybrid" || raw === "relational") return raw
  return "event_store"
}
