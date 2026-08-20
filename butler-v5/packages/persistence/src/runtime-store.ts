import { and, asc, eq, gt } from "drizzle-orm"
import type { ScopedGrantRecord } from "@butler/domain/governance/types.js"
import { grantMatchesAction, type ActionRequest } from "@butler/domain/governance/types.js"
import type {
  RunStatus,
  RuntimeStore,
  StepKind,
  StepStatus,
  StoredMessage,
  StoredRun,
  StoredStep,
  TriggerSource,
} from "@butler/domain/runtime.js"
import type { ButlerDb } from "./db.js"
import { auditEvents, conversations, messages, runs, scopedGrants, steps } from "./schema.js"

export class RuntimeVersionConflictError extends Error {
  constructor(
    public readonly runId: string,
    public readonly expectedVersion: number,
  ) {
    super(`runtime version conflict on run ${runId} at expected version ${expectedVersion}`)
  }
}

function toStoredRun(row: typeof runs.$inferSelect): StoredRun {
  return {
    id: row.runId,
    conversationId: row.conversationId,
    parentRunId: row.parentRunId,
    triggerSource: row.triggerSource as TriggerSource,
    idempotencyKey: row.idempotencyKey,
    subject: row.subject,
    goal: row.goal,
    budget: row.budget as Readonly<Record<string, unknown>>,
    deadline: row.deadline,
    status: row.status as RunStatus,
    version: row.version,
    createdAt: row.createdAt,
    updatedAt: row.updatedAt,
  }
}

function toStoredStep(row: typeof steps.$inferSelect): StoredStep {
  return {
    id: row.stepId,
    runId: row.runId,
    kind: row.kind as StepKind,
    status: row.status as StepStatus,
    input: row.input as Readonly<Record<string, unknown>>,
    output: (row.output as Readonly<Record<string, unknown>> | null) ?? null,
    createdAt: row.createdAt,
    updatedAt: row.updatedAt,
  }
}

function toScopedGrant(row: typeof scopedGrants.$inferSelect): ScopedGrantRecord {
  const scope = row.scope as {
    readonly capabilities?: readonly string[]
    readonly paths?: readonly string[]
    readonly network?: "deny" | "allow"
    readonly networkHosts?: readonly string[]
    readonly maxUses?: number
    readonly digest?: string
  }
  return {
    id: row.grantId,
    runId: row.runId,
    subject: row.subject,
    scope: {
      capabilities: scope.capabilities ?? [],
      ...(scope.paths ? { paths: scope.paths } : {}),
      ...(scope.network ? { network: scope.network } : {}),
      ...(scope.networkHosts ? { networkHosts: scope.networkHosts } : {}),
      ...(scope.maxUses !== undefined ? { maxUses: scope.maxUses } : {}),
      ...(scope.digest ? { digest: scope.digest } : {}),
    },
    remainingUses: row.remainingUses,
    expiresAtMs: row.expiresAt.getTime(),
    createdAtMs: row.createdAt.getTime(),
  }
}

function toStoredMessage(row: typeof messages.$inferSelect): StoredMessage {
  return {
    id: row.messageId,
    conversationId: row.conversationId,
    role: row.role as StoredMessage["role"],
    content: row.content as Readonly<Record<string, unknown>>,
    triggerSource: (row.triggerSource as TriggerSource | null) ?? null,
    idempotencyKey: row.idempotencyKey,
    createdAt: row.createdAt,
  }
}

export function createRuntimeStore(db: ButlerDb): RuntimeStore {
  return {
    async createConversationWithUserMessage(input) {
      const existing = await db
        .select()
        .from(messages)
        .where(eq(messages.idempotencyKey, input.idempotencyKey))
        .limit(1)
      const hit = existing[0]
      if (hit) {
        return { conversationId: hit.conversationId, messageId: hit.messageId }
      }

      await db.insert(conversations).values({
        conversationId: input.conversationId,
        subject: input.subject,
        createdAt: input.createdAt,
        updatedAt: input.createdAt,
      })
      await db.insert(messages).values({
        messageId: input.messageId,
        conversationId: input.conversationId,
        role: "user",
        content: input.content,
        triggerSource: input.triggerSource,
        idempotencyKey: input.idempotencyKey,
        createdAt: input.createdAt,
      })
      return { conversationId: input.conversationId, messageId: input.messageId }
    },

    async createRun(input) {
      const existing = await db
        .select()
        .from(runs)
        .where(eq(runs.idempotencyKey, input.idempotencyKey))
        .limit(1)
      const hit = existing[0]
      if (hit) {
        return toStoredRun(hit)
      }

      const [row] = await db
        .insert(runs)
        .values({
          runId: input.id,
          conversationId: input.conversationId,
          parentRunId: input.parentRunId,
          triggerSource: input.triggerSource,
          idempotencyKey: input.idempotencyKey,
          subject: input.subject,
          goal: input.goal,
          status: "queued",
          budget: input.budget,
          deadline: input.deadline,
          version: 1,
          createdAt: input.createdAt,
          updatedAt: input.createdAt,
        })
        .returning()
      if (!row) {
        throw new Error("failed to create run")
      }
      return toStoredRun(row)
    },

    async transitionRunStatus(runId, expectedVersion, status, updatedAt) {
      const updated = await db
        .update(runs)
        .set({ status, version: expectedVersion + 1, updatedAt })
        .where(and(eq(runs.runId, runId), eq(runs.version, expectedVersion)))
        .returning()
      const row = updated[0]
      if (!row) {
        throw new RuntimeVersionConflictError(runId, expectedVersion)
      }
      return toStoredRun(row)
    },

    async createStep(input) {
      const [row] = await db
        .insert(steps)
        .values({
          stepId: input.id,
          runId: input.runId,
          kind: input.kind,
          status: input.status,
          input: input.input,
          output: null,
          createdAt: input.createdAt,
          updatedAt: input.createdAt,
        })
        .returning()
      if (!row) {
        throw new Error("failed to create step")
      }
      return toStoredStep(row)
    },

    async listMessages(conversationId) {
      const rows = await db
        .select()
        .from(messages)
        .where(eq(messages.conversationId, conversationId))
        .orderBy(asc(messages.createdAt))
      return rows.map(toStoredMessage)
    },

    async appendMessage(input) {
      if (input.idempotencyKey) {
        const existing = await db
          .select()
          .from(messages)
          .where(eq(messages.idempotencyKey, input.idempotencyKey))
          .limit(1)
        const hit = existing[0]
        if (hit) return toStoredMessage(hit)
      }
      await db.insert(messages).values({
        messageId: input.messageId,
        conversationId: input.conversationId,
        role: input.role,
        content: input.content,
        triggerSource: input.triggerSource,
        idempotencyKey: input.idempotencyKey,
        createdAt: input.createdAt,
      })
      const rows = await db
        .select()
        .from(messages)
        .where(eq(messages.messageId, input.messageId))
        .limit(1)
      const row = rows[0]
      if (!row) throw new Error("failed to append message")
      return toStoredMessage(row)
    },

    async getRun(runId) {
      const rows = await db.select().from(runs).where(eq(runs.runId, runId)).limit(1)
      const row = rows[0]
      return row ? toStoredRun(row) : null
    },

    async getStep(stepId) {
      const rows = await db.select().from(steps).where(eq(steps.stepId, stepId)).limit(1)
      const row = rows[0]
      return row ? toStoredStep(row) : null
    },

    async updateStep(input) {
      const patch: {
        status?: StepStatus
        output?: Record<string, unknown> | null
        updatedAt: Date
      } = { updatedAt: input.updatedAt }
      if (input.status !== undefined) patch.status = input.status
      if (input.output !== undefined) patch.output = input.output as Record<string, unknown> | null
      const updated = await db
        .update(steps)
        .set(patch)
        .where(eq(steps.stepId, input.stepId))
        .returning()
      const row = updated[0]
      if (!row) throw new Error(`step not found: ${input.stepId}`)
      return toStoredStep(row)
    },

    async listWaitingApprovalSteps() {
      const rows = await db
        .select()
        .from(steps)
        .where(and(eq(steps.kind, "approval"), eq(steps.status, "waiting")))
        .orderBy(asc(steps.createdAt))
      return rows.map(toStoredStep)
    },

    async listWaitingApprovalStepsForConversation(conversationId) {
      const rows = await db
        .select({ step: steps })
        .from(steps)
        .innerJoin(runs, eq(steps.runId, runs.runId))
        .where(
          and(
            eq(runs.conversationId, conversationId),
            eq(steps.kind, "approval"),
            eq(steps.status, "waiting"),
          ),
        )
        .orderBy(asc(steps.createdAt))
      return rows.map((row) => toStoredStep(row.step))
    },

    async createScopedGrant(input) {
      await db.insert(scopedGrants).values({
        grantId: input.grantId,
        runId: input.runId,
        subject: input.subject,
        scope: input.scope,
        remainingUses: input.remainingUses,
        expiresAt: input.expiresAt,
        createdAt: input.createdAt,
      })
      const rows = await db
        .select()
        .from(scopedGrants)
        .where(eq(scopedGrants.grantId, input.grantId))
        .limit(1)
      const row = rows[0]
      if (!row) throw new Error("failed to create scoped grant")
      return toScopedGrant(row)
    },

    async findActiveGrant(input) {
      const rows = await db
        .select()
        .from(scopedGrants)
        .where(
          and(
            eq(scopedGrants.runId, input.runId),
            eq(scopedGrants.subject, input.subject),
            gt(scopedGrants.expiresAt, input.now),
          ),
        )
        .orderBy(asc(scopedGrants.createdAt))
      for (const row of rows) {
        const grant = toScopedGrant(row)
        if (grant.remainingUses !== null && grant.remainingUses <= 0) continue
        if (!grant.scope.capabilities.includes(input.capability)) continue
        if (input.resource !== undefined || input.digest !== undefined) {
          const probe: ActionRequest = {
            kind: "read",
            capability: input.capability,
            subject: input.subject,
            resource: input.resource ?? "",
            risk: "low",
            digest: input.digest ?? "",
            payload: {},
          }
          if (!grantMatchesAction(grant, probe)) continue
        }
        return grant
      }
      return null
    },

    async appendAuditEvent(input) {
      await db.insert(auditEvents).values({
        auditId: input.auditId,
        runId: input.runId,
        conversationId: input.conversationId,
        action: input.action,
        subject: input.subject,
        detail: input.detail,
        createdAt: input.createdAt,
      })
    },

    async updateScopedGrantRemainingUses(grantId, remainingUses) {
      await db
        .update(scopedGrants)
        .set({ remainingUses })
        .where(eq(scopedGrants.grantId, grantId))
    },
  }
}
