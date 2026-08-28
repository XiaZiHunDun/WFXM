import { and, asc, desc, eq, gt, inArray, isNull, lt, isNotNull } from "drizzle-orm"
import type { ScopedGrantRecord } from "@butler/domain/governance/types.js"
import { grantMatchesAction, type ActionRequest } from "@butler/domain/governance/types.js"
import { scopedGrantScopeTargetsMcpServer } from "@butler/domain/governance/mcp-tool-capability.js"
import {
  ACTIVE_MAIN_RUN_STATUSES,
  inferProjectIdFromConversationId,
  type RunStatus,
  type RuntimeStore,
  type StepKind,
  type StepStatus,
  type StoredConversation,
  type StoredMessage,
  type StoredRun,
  type StoredStep,
  type TriggerSource,
} from "@butler/domain/runtime.js"
import type { ButlerDb } from "./db.js"
import { auditEvents, conversations, messages, runs, scopedGrants, steps } from "./schema.js"
import { redactTraceValue } from "@butler/domain/observability/local-trace.js"

/**
 * Durable context artifact (transcript) — P2 secret scan.
 * Message content is always scanned+redacted before persisting so secrets never
 * land in the durable transcript; the live loop still reads raw in-memory output.
 */
function redactStoredContent(
  content: Readonly<Record<string, unknown>>,
): Readonly<Record<string, unknown>> {
  return redactTraceValue(content, 0) as Readonly<Record<string, unknown>>
}

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
    readonly paths?: readonly string[]
    readonly network?: "deny" | "allow"
    readonly networkHosts?: readonly string[]
    readonly maxUses?: number
    readonly digest?: string
    readonly mcp?: { readonly serverId: string; readonly toolName: string }
    /** Legacy backfill fallback only; new rows never set this. */
    readonly capabilities?: readonly string[]
  }
  // D2.2: capability column is source-of-truth; legacy rows (pre-migration) may still have
  // scope.capabilities as a string array — fall back to index 0 if column is NULL.
  const legacyCapability =
    Array.isArray(scope.capabilities) && scope.capabilities.length > 0
      ? scope.capabilities[0]
      : ""
  return {
    id: row.grantId,
    capability: row.capability ?? legacyCapability,
    runId: row.runId,
    subject: row.subject,
    scope: {
      ...(scope.paths ? { paths: scope.paths } : {}),
      ...(scope.network ? { network: scope.network } : {}),
      ...(scope.networkHosts ? { networkHosts: scope.networkHosts } : {}),
      ...(scope.maxUses !== undefined ? { maxUses: scope.maxUses } : {}),
      ...(scope.digest ? { digest: scope.digest } : {}),
      ...(scope.mcp ? { mcp: scope.mcp } : {}),
    },
    remainingUses: row.remainingUses,
    expiresAtMs: row.expiresAt.getTime(),
    createdAtMs: row.createdAt.getTime(),
    delegable: row.delegable ?? false,
    approvalId: row.approvalId ?? null,
    sandboxProfile: row.sandboxProfile ?? null,
    networkAllowlist: Array.isArray(row.networkAllowlist) ? row.networkAllowlist : null,
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

      const existingConv = await db
        .select()
        .from(conversations)
        .where(eq(conversations.conversationId, input.conversationId))
        .limit(1)
      if (!existingConv[0]) {
        const projectId =
          input.projectId ?? inferProjectIdFromConversationId(input.conversationId)
        await db.insert(conversations).values({
          conversationId: input.conversationId,
          projectId,
          subject: input.subject,
          createdAt: input.createdAt,
          updatedAt: input.createdAt,
        })
      } else {
        const projectId =
          input.projectId ??
          existingConv[0].projectId ??
          inferProjectIdFromConversationId(input.conversationId)
        await db
          .update(conversations)
          .set({ updatedAt: input.createdAt, subject: input.subject, projectId })
          .where(eq(conversations.conversationId, input.conversationId))
      }
      await db.insert(messages).values({
        messageId: input.messageId,
        conversationId: input.conversationId,
        role: "user",
        content: redactStoredContent(input.content),
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

    async listConversationsByProject(input) {
      const limit = Math.min(Math.max(input.limit ?? 50, 1), 200)
      const rows = await db
        .select()
        .from(conversations)
        .where(eq(conversations.projectId, input.projectId.trim()))
        .orderBy(desc(conversations.updatedAt))
        .limit(limit)
      return rows.map(
        (row): StoredConversation => ({
          id: row.conversationId,
          projectId: row.projectId,
          subject: row.subject,
          createdAt: row.createdAt,
          updatedAt: row.updatedAt,
        }),
      )
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
        content: redactStoredContent(input.content),
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

    async findActiveMainRun(conversationId) {
      const rows = await db
        .select()
        .from(runs)
        .where(
          and(
            eq(runs.conversationId, conversationId),
            isNull(runs.parentRunId),
            inArray(runs.status, [...ACTIVE_MAIN_RUN_STATUSES]),
          ),
        )
        .limit(1)
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
        capability: input.capability,
        scope: input.scope,
        remainingUses: input.remainingUses,
        expiresAt: input.expiresAt,
        createdAt: input.createdAt,
        delegable: input.delegable ?? false,
        approvalId: input.approvalId ?? null,
        sandboxProfile: input.sandboxProfile ?? null,
        networkAllowlist: input.networkAllowlist ?? null,
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
            eq(scopedGrants.capability, input.capability),
            gt(scopedGrants.expiresAt, input.now),
          ),
        )
        .orderBy(asc(scopedGrants.createdAt))
      for (const row of rows) {
        const grant = toScopedGrant(row)
        if (grant.remainingUses !== null && grant.remainingUses <= 0) continue
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
        detail: redactTraceValue(input.detail, 0),
        createdAt: input.createdAt,
      })
    },

    async updateScopedGrantRemainingUses(grantId, remainingUses) {
      await db
        .update(scopedGrants)
        .set({ remainingUses })
        .where(eq(scopedGrants.grantId, grantId))
    },

    async revokeScopedGrantsForMcpServer(serverId, now) {
      const rows = await db
        .select()
        .from(scopedGrants)
        .where(gt(scopedGrants.expiresAt, now))
      let revoked = 0
      for (const row of rows) {
        const grant = toScopedGrant(row)
        if (grant.remainingUses !== null && grant.remainingUses <= 0) {
          continue
        }
        if (!scopedGrantScopeTargetsMcpServer(grant.scope, serverId)) {
          continue
        }
        await db
          .update(scopedGrants)
          .set({ remainingUses: 0 })
          .where(eq(scopedGrants.grantId, row.grantId))
        revoked += 1
      }
      return revoked
    },

    async countActiveScopedGrantsForMcpServer(serverId, now) {
      const rows = await db
        .select()
        .from(scopedGrants)
        .where(gt(scopedGrants.expiresAt, now))
      let count = 0
      for (const row of rows) {
        const grant = toScopedGrant(row)
        if (grant.remainingUses !== null && grant.remainingUses <= 0) {
          continue
        }
        if (scopedGrantScopeTargetsMcpServer(grant.scope, serverId)) {
          count += 1
        }
      }
      return count
    },

    async revokeScopedGrantsForCapability(capability, now) {
      const rows = await db
        .select()
        .from(scopedGrants)
        .where(
          and(
            gt(scopedGrants.expiresAt, now),
            eq(scopedGrants.capability, capability),
          ),
        )
      let revoked = 0
      for (const row of rows) {
        if (row.remainingUses !== null && row.remainingUses <= 0) {
          continue
        }
        await db
          .update(scopedGrants)
          .set({ remainingUses: 0 })
          .where(eq(scopedGrants.grantId, row.grantId))
        revoked += 1
      }
      return revoked
    },

    async listRunsPastDeadline(now) {
      const rows = await db
        .select()
        .from(runs)
        .where(
          and(
            isNotNull(runs.deadline),
            lt(runs.deadline, now),
            inArray(runs.status, [...ACTIVE_MAIN_RUN_STATUSES]),
          ),
        )
        .orderBy(asc(runs.deadline))
      return rows.map(toStoredRun)
    },
  }
}
