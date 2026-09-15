import type { ScopedGrantRecord, ScopedGrantScope } from "../governance/types.js"
import type { RunStatus, StepKind, StepStatus, TriggerSource } from "./types.js"

/** D66 T1a: read-side audit event record (returned by listRecentAuditEvents). */
export interface AuditEventRecord {
  readonly auditId: string
  readonly runId: string | null
  readonly conversationId: string | null
  readonly action: string
  readonly subject: string
  readonly detail: Readonly<Record<string, unknown>>
  readonly createdAt: Date
  // D63 T3 (audit #9 F-04): optional correlationId for request-scoped
  // audit trail. Mirrors the audit_events.correlation_id column.
  readonly correlationId?: string | null
}

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
    /** D2.2 first-class capability column mirror (DESIGN §10.3). */
    readonly capability: string
    readonly scope: ScopedGrantScope
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
    // D63 T3 (audit #9 F-04): optional correlationId column for
    // request-scoped audit trail. New `audit_events.correlation_id`
    // column added by migration 0013. Routes thread inbound
    // messageId/conversationId as correlationId; thread through
    // remaining emit sites in future cycles.
    readonly correlationId?: string | null
  }) => Promise<void>
  /** D66 T1a — list recent audit events for replay + acceptance verification.
   *  Filters: actor (matches `subject` column), conversationId, windowMs
   *  (createdAt within the last windowMs from now), limit (cap). */
  readonly listRecentAuditEvents: (input: {
    readonly actor?: string
    readonly windowMs: number
    readonly conversationId?: string
    readonly limit?: number
  }) => Promise<readonly AuditEventRecord[]>
  readonly updateScopedGrantRemainingUses: (
    grantId: string,
    remainingUses: number | null,
  ) => Promise<void>
  /** P3: expire MCP grants bound to a server (sets remainingUses=0). */
  readonly revokeScopedGrantsForMcpServer: (
    serverId: string,
    now: Date,
  ) => Promise<number>
  /** P3: count non-exhausted MCP grants for a server (for Owner status). */
  readonly countActiveScopedGrantsForMcpServer: (
    serverId: string,
    now: Date,
  ) => Promise<number>
  /** P3-2: expire grants whose scope targets a capability (sets remainingUses=0)
   * when that capability provider is uninstalled. */
  readonly revokeScopedGrantsForCapability: (
    capability: string,
    now: Date,
  ) => Promise<number>
  /** Active main/child Runs whose deadline is strictly before `now`. */
  readonly listRunsPastDeadline: (now: Date) => Promise<readonly StoredRun[]>
  /** D4-arch-align: child Runs of the given parent (parentRunId == runId).
   *  Used by cancelRun cascade + UI tree. */
  readonly findChildRuns: (parentRunId: string) => Promise<readonly StoredRun[]>
  /** D6-arch-align §20 #7: tx-aware variants for atomic state-change+audit
   *  composition. Caller is responsible for opening a transaction
   *  (e.g. `store.withTransaction(async (tx) => { ... })`) and passing the
   *  same tx to both state-change and audit write so the row + its audit
   *  trail are atomic. */
  readonly appendAuditEventInTx: (
    tx: RuntimeTx,
    input: {
      readonly auditId: string
      readonly runId: string | null
      readonly conversationId: string | null
      readonly action: string
      readonly subject: string
      readonly detail: Readonly<Record<string, unknown>>
      readonly createdAt: Date
      // D63 T3 (audit #9 F-04): see appendAuditEvent above — mirrors the
      // same nullable correlationId for transactional audit writes.
      readonly correlationId?: string | null
    },
  ) => Promise<void>
  readonly transitionRunStatusInTx: (
    tx: RuntimeTx,
    runId: string,
    expectedVersion: number,
    to: StoredRun["status"],
    updatedAt: Date,
  ) => Promise<StoredRun>
  /** Run a function in a single DB transaction. The callback receives a
   *  Drizzle tx object that can be passed to any `*InTx` store method. */
  readonly withTransaction: <T>(fn: (tx: RuntimeTx) => Promise<T>) => Promise<T>
}

/** Drizzle transaction handle (PgliteDatabase | NodePgDatabase `tx`). */
type RuntimeTx = unknown

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
