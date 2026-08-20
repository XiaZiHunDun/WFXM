import { and, asc, eq } from "drizzle-orm"
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
import { conversations, messages, runs, steps } from "./schema.js"

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
  }
}
