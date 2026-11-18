import { desc, eq } from "drizzle-orm"
import type {
  PiTaskPendingStep,
  PiTaskSessionRecord,
  PiTaskSessionSnapshot,
  PiTaskSessionStatus,
  PiTaskSessionStore,
} from "@butler/ports/core/pi-task-session.js"
import type { ButlerDb } from "./db.js"
import { taskSessions } from "./schema.js"

function toRecord(row: typeof taskSessions.$inferSelect): PiTaskSessionRecord {
  return {
    taskId: row.taskId,
    projectId: row.projectId,
    cwd: row.cwd,
    status: row.status as PiTaskSessionStatus,
    snapshot: row.snapshot as PiTaskSessionSnapshot,
    pendingStep: (row.pendingStep as PiTaskPendingStep | null) ?? null,
    createdAt: row.createdAt.toISOString(),
    updatedAt: row.updatedAt.toISOString(),
  }
}

/** Butler-side durable store for pi task sessions. */
export class DrizzlePiTaskSessionStore implements PiTaskSessionStore {
  constructor(private readonly db: ButlerDb) {}

  async load(taskId: string): Promise<PiTaskSessionRecord | null> {
    const rows = await this.db
      .select()
      .from(taskSessions)
      .where(eq(taskSessions.taskId, taskId))
      .limit(1)
    const row = rows[0]
    return row ? toRecord(row) : null
  }

  async save(record: PiTaskSessionRecord): Promise<void> {
    const values = {
      taskId: record.taskId,
      projectId: record.projectId,
      cwd: record.cwd,
      status: record.status,
      snapshot: record.snapshot,
      pendingStep: record.pendingStep,
      createdAt: new Date(record.createdAt),
      updatedAt: new Date(record.updatedAt),
    }
    await this.db
      .insert(taskSessions)
      .values(values)
      .onConflictDoUpdate({
        target: taskSessions.taskId,
        set: {
          projectId: values.projectId,
          cwd: values.cwd,
          status: values.status,
          snapshot: values.snapshot,
          pendingStep: values.pendingStep,
          updatedAt: values.updatedAt,
        },
      })
  }

  async delete(taskId: string): Promise<void> {
    await this.db.delete(taskSessions).where(eq(taskSessions.taskId, taskId))
  }

  async listByStatus(status: PiTaskSessionStatus): Promise<readonly PiTaskSessionRecord[]> {
    const rows = await this.db
      .select()
      .from(taskSessions)
      .where(eq(taskSessions.status, status))
      .orderBy(desc(taskSessions.updatedAt))
    return rows.map(toRecord)
  }
}
