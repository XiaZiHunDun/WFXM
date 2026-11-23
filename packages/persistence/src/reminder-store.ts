import { and, asc, eq, isNull, lte, or, sql } from "drizzle-orm"
import type { ButlerDb } from "./db.js"
import { reminders } from "./schema.js"

export type ReminderRepeat = "once" | "daily" | "weekly"
export type ReminderStatus = "active" | "done" | "cancelled"

export interface ReminderRecord {
  readonly id: string
  readonly subject: string
  readonly wechatUserId: string
  readonly conversationId: string
  readonly content: string
  readonly fireAtMs: number
  readonly repeat: ReminderRepeat
  readonly status: ReminderStatus
  readonly attemptCount: number
  readonly lastAttemptAtMs: number | null
  readonly lastError: string | null
  readonly firedAtMs: number | null
  readonly createdAtMs: number
  readonly updatedAtMs: number
}

export interface ReminderStore {
  readonly create: (record: ReminderRecord) => Promise<ReminderRecord>
  readonly get: (id: string) => Promise<ReminderRecord | null>
  readonly listActiveBySubject: (input: {
    readonly subject: string
    readonly limit?: number
  }) => Promise<readonly ReminderRecord[]>
  /** All active reminders (owner debugging view). */
  readonly listActive: (input?: { readonly limit?: number }) => Promise<readonly ReminderRecord[]>
  readonly countActiveBySubject: (subject: string) => Promise<number>
  /** Active reminders whose time has come and whose retry cooldown elapsed. */
  readonly listDue: (input: {
    readonly nowMs: number
    readonly retryCooldownMs: number
    readonly limit?: number
  }) => Promise<readonly ReminderRecord[]>
  /** once → done; daily/weekly → advance fire_at and reset retry state. */
  readonly markFired: (input: {
    readonly id: string
    readonly nextFireAtMs?: number
    readonly firedAtMs: number
  }) => Promise<void>
  readonly markAttemptFailed: (input: {
    readonly id: string
    readonly error: string
    readonly attemptedAtMs: number
  }) => Promise<void>
  readonly cancel: (input: { readonly id: string; readonly subject: string }) => Promise<boolean>
}

function toRecord(row: typeof reminders.$inferSelect): ReminderRecord {
  return {
    id: row.reminderId,
    subject: row.subject,
    wechatUserId: row.wechatUserId,
    conversationId: row.conversationId,
    content: row.content,
    fireAtMs: row.fireAt.getTime(),
    repeat: row.repeat as ReminderRepeat,
    status: row.status as ReminderStatus,
    attemptCount: row.attemptCount,
    lastAttemptAtMs: row.lastAttemptAt?.getTime() ?? null,
    lastError: row.lastError,
    firedAtMs: row.firedAt?.getTime() ?? null,
    createdAtMs: row.createdAt.getTime(),
    updatedAtMs: row.updatedAt.getTime(),
  }
}

export function createReminderStore(db: ButlerDb): ReminderStore {
  return {
    async create(record) {
      await db.insert(reminders).values({
        reminderId: record.id,
        subject: record.subject,
        wechatUserId: record.wechatUserId,
        conversationId: record.conversationId,
        content: record.content,
        fireAt: new Date(record.fireAtMs),
        repeat: record.repeat,
        status: record.status,
        attemptCount: record.attemptCount,
        lastAttemptAt: record.lastAttemptAtMs === null ? null : new Date(record.lastAttemptAtMs),
        lastError: record.lastError,
        firedAt: record.firedAtMs === null ? null : new Date(record.firedAtMs),
        createdAt: new Date(record.createdAtMs),
        updatedAt: new Date(record.updatedAtMs),
      })
      return record
    },

    async get(id) {
      const rows = await db.select().from(reminders).where(eq(reminders.reminderId, id)).limit(1)
      const row = rows[0]
      return row ? toRecord(row) : null
    },

    async listActiveBySubject(input) {
      const rows = await db
        .select()
        .from(reminders)
        .where(and(eq(reminders.subject, input.subject), eq(reminders.status, "active")))
        .orderBy(asc(reminders.fireAt))
        .limit(input.limit ?? 50)
      return rows.map(toRecord)
    },

    async listActive(input) {
      const rows = await db
        .select()
        .from(reminders)
        .where(eq(reminders.status, "active"))
        .orderBy(asc(reminders.fireAt))
        .limit(input?.limit ?? 100)
      return rows.map(toRecord)
    },

    async countActiveBySubject(subject) {
      const rows = await db
        .select({ count: sql<number>`count(*)::int` })
        .from(reminders)
        .where(and(eq(reminders.subject, subject), eq(reminders.status, "active")))
      return rows[0]?.count ?? 0
    },

    async listDue(input) {
      const cutoff = new Date(input.nowMs - input.retryCooldownMs)
      const rows = await db
        .select()
        .from(reminders)
        .where(
          and(
            eq(reminders.status, "active"),
            lte(reminders.fireAt, new Date(input.nowMs)),
            or(isNull(reminders.lastAttemptAt), lte(reminders.lastAttemptAt, cutoff)),
          ),
        )
        .orderBy(asc(reminders.fireAt))
        .limit(input.limit ?? 20)
      return rows.map(toRecord)
    },

    async markFired(input) {
      const recurring = input.nextFireAtMs !== undefined
      await db
        .update(reminders)
        .set({
          status: recurring ? "active" : "done",
          ...(recurring ? { fireAt: new Date(input.nextFireAtMs as number) } : {}),
          firedAt: new Date(input.firedAtMs),
          attemptCount: 0,
          lastAttemptAt: null,
          lastError: null,
          updatedAt: new Date(input.firedAtMs),
        })
        .where(eq(reminders.reminderId, input.id))
    },

    async markAttemptFailed(input) {
      await db
        .update(reminders)
        .set({
          attemptCount: sql`${reminders.attemptCount} + 1`,
          lastAttemptAt: new Date(input.attemptedAtMs),
          lastError: input.error,
          updatedAt: new Date(input.attemptedAtMs),
        })
        .where(eq(reminders.reminderId, input.id))
    },

    async cancel(input) {
      const rows = await db
        .update(reminders)
        .set({ status: "cancelled", updatedAt: new Date() })
        .where(
          and(
            eq(reminders.reminderId, input.id),
            eq(reminders.subject, input.subject),
            eq(reminders.status, "active"),
          ),
        )
        .returning()
      return rows.length > 0
    },
  }
}
