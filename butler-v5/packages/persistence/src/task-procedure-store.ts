import { and, desc, eq } from "drizzle-orm"
import type {
  ProcedureRecord,
  ProcedureStepTemplate,
  TaskRecord,
  TaskStatus,
} from "@butler/domain/knowledge/task-procedure.js"
import type { ButlerDb } from "./db.js"
import { procedures, tasks } from "./schema.js"

export interface ProcedureStore {
  readonly create: (record: ProcedureRecord) => Promise<ProcedureRecord>
  readonly get: (procedureId: string) => Promise<ProcedureRecord | null>
  readonly list: (limit?: number) => Promise<readonly ProcedureRecord[]>
}

export interface TaskStore {
  readonly create: (record: TaskRecord) => Promise<TaskRecord>
  readonly get: (taskId: string) => Promise<TaskRecord | null>
  readonly update: (record: TaskRecord) => Promise<TaskRecord>
  readonly listBySubject: (input: {
    readonly subject: string
    readonly status?: TaskStatus
    readonly limit?: number
  }) => Promise<readonly TaskRecord[]>
}

function toProcedure(row: typeof procedures.$inferSelect): ProcedureRecord {
  return {
    id: row.procedureId,
    name: row.name,
    version: row.version,
    steps: row.steps as readonly ProcedureStepTemplate[],
    createdAt: row.createdAt.getTime(),
  }
}

function toTask(row: typeof tasks.$inferSelect): TaskRecord {
  return {
    id: row.taskId,
    subject: row.subject,
    title: row.title,
    goal: row.goal,
    status: row.status as TaskStatus,
    conversationId: row.conversationId,
    procedureId: row.procedureId,
    procedureStepIndex: row.procedureStepIndex,
    createdAt: row.createdAt.getTime(),
    updatedAt: row.updatedAt.getTime(),
  }
}

export function createProcedureStore(db: ButlerDb): ProcedureStore {
  return {
    async create(record) {
      await db.insert(procedures).values({
        procedureId: record.id,
        name: record.name,
        version: record.version,
        steps: record.steps,
        createdAt: new Date(record.createdAt),
      })
      return record
    },
    async get(procedureId) {
      const rows = await db
        .select()
        .from(procedures)
        .where(eq(procedures.procedureId, procedureId))
        .limit(1)
      const row = rows[0]
      return row ? toProcedure(row) : null
    },
    async list(limit = 50) {
      const rows = await db
        .select()
        .from(procedures)
        .orderBy(desc(procedures.createdAt))
        .limit(limit)
      return rows.map(toProcedure)
    },
  }
}

export function createTaskStore(db: ButlerDb): TaskStore {
  return {
    async create(record) {
      await db.insert(tasks).values({
        taskId: record.id,
        subject: record.subject,
        title: record.title,
        goal: record.goal,
        status: record.status,
        conversationId: record.conversationId,
        procedureId: record.procedureId,
        procedureStepIndex: record.procedureStepIndex,
        createdAt: new Date(record.createdAt),
        updatedAt: new Date(record.updatedAt),
      })
      return record
    },
    async get(taskId) {
      const rows = await db.select().from(tasks).where(eq(tasks.taskId, taskId)).limit(1)
      const row = rows[0]
      return row ? toTask(row) : null
    },
    async update(record) {
      await db
        .update(tasks)
        .set({
          title: record.title,
          goal: record.goal,
          status: record.status,
          conversationId: record.conversationId,
          procedureId: record.procedureId,
          procedureStepIndex: record.procedureStepIndex,
          updatedAt: new Date(record.updatedAt),
        })
        .where(eq(tasks.taskId, record.id))
      return record
    },
    async listBySubject(input) {
      const limit = input.limit ?? 50
      const rows = input.status
        ? await db
            .select()
            .from(tasks)
            .where(and(eq(tasks.subject, input.subject), eq(tasks.status, input.status)))
            .orderBy(desc(tasks.updatedAt))
            .limit(limit)
        : await db
            .select()
            .from(tasks)
            .where(eq(tasks.subject, input.subject))
            .orderBy(desc(tasks.updatedAt))
            .limit(limit)
      return rows.map(toTask)
    },
  }
}
