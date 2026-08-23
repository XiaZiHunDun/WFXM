import type { ScopedGrantRecord } from "../governance/types.js"
import type { RunStatus, StepKind, StepStatus, TriggerSource } from "./types.js"

/** Main-Run statuses that block starting another main Run in the same conversation. */
export const ACTIVE_MAIN_RUN_STATUSES: readonly RunStatus[] = [
  "queued",
  "running",
  "waiting_approval",
  "waiting_external",
]

export function isActiveMainRunStatus(status: RunStatus): boolean {
  return (ACTIVE_MAIN_RUN_STATUSES as readonly string[]).includes(status)
}

export interface StoredMessage {
  readonly id: string
  readonly conversationId: string
  readonly role: "user" | "assistant" | "system" | "tool"
  readonly content: Readonly<Record<string, unknown>>
  readonly triggerSource: TriggerSource | null
  readonly idempotencyKey: string | null
  readonly createdAt: Date
}

export interface StoredConversation {
  readonly id: string
  readonly projectId: string | null
  readonly subject: string
  readonly createdAt: Date
  readonly updatedAt: Date
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
    readonly projectId?: string
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
  readonly listConversationsByProject: (input: {
    readonly projectId: string
    readonly limit?: number
  }) => Promise<readonly StoredConversation[]>
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
  /** Active main Run for a conversation (`parentRunId` null + non-terminal status), if any. */
  readonly findActiveMainRun: (conversationId: string) => Promise<StoredRun | null>
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
    readonly delegable?: boolean
    readonly approvalId?: string | null
    readonly sandboxProfile?: string | null
    readonly networkAllowlist?: readonly string[] | null
  }) => Promise<ScopedGrantRecord>
  readonly findActiveGrant: (input: {
    readonly runId: string
    readonly subject: string
    readonly capability: string
    readonly resource?: string
    readonly digest?: string
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
  /** P3: expire MCP grants bound to a server (sets remainingUses=0). */
  readonly revokeScopedGrantsForMcpServer: (
    serverId: string,
    now: Date,
  ) => Promise<number>
  /** Active main/child Runs whose deadline is strictly before `now`. */
  readonly listRunsPastDeadline: (now: Date) => Promise<readonly StoredRun[]>
}

export type ReadModelSource = "event_store" | "hybrid" | "relational"

/** Production default: 0002 relational messages (long sessions / multi-project). */
export const DEFAULT_READ_MODEL_SOURCE: ReadModelSource = "relational"

export function resolveReadModelSource(
  env: Readonly<Record<string, string | undefined>>,
): ReadModelSource {
  const raw = (env["BUTLER_V5_READ_MODEL"] ?? DEFAULT_READ_MODEL_SOURCE).trim().toLowerCase()
  if (raw === "event_store" || raw === "relational") return raw
  if (raw === "hybrid") return "hybrid"
  return DEFAULT_READ_MODEL_SOURCE
}
