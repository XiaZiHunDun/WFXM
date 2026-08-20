import { and, asc, eq, inArray, lte, sql } from "drizzle-orm"
import type { ButlerDb } from "./db.js"
import { outbox } from "./schema.js"

export type OutboxMessage = typeof outbox.$inferSelect

export interface EnqueueInput {
  readonly streamId: string
  readonly aggregateType: string
  readonly payload: Record<string, unknown>
}

const BASE_BACKOFF_MS = 1_000
const MAX_BACKOFF_MS = 60_000

/**
 * Insert a new outbox message in 'pending' state.
 */
export async function enqueueOutbox(db: ButlerDb, input: EnqueueInput): Promise<string> {
  const messageId = crypto.randomUUID()
  const now = new Date()
  await db.insert(outbox).values({
    messageId,
    streamId: input.streamId,
    aggregateType: input.aggregateType,
    payload: input.payload,
    status: "pending",
    attemptCount: 0,
    nextAttemptAt: now,
    leaseOwner: null,
    leaseUntil: null,
    lastError: null,
    createdAt: now,
    deliveredAt: null,
  })
  return messageId
}

/**
 * Atomically claim up to `limit` pending messages whose backoff has elapsed and
 * lease has expired. Select + update run in one transaction; limit is applied
 * in SQL (ordered by next_attempt_at).
 */
export async function claimOutbox(
  db: ButlerDb,
  workerId: string,
  leaseMs: number,
  limit = 10,
): Promise<OutboxMessage[]> {
  const now = new Date()
  const leaseUntil = new Date(now.getTime() + leaseMs)
  return db.transaction(async (tx) => {
    const candidates = await tx
      .select()
      .from(outbox)
      .where(
        and(
          eq(outbox.status, "pending"),
          lte(outbox.nextAttemptAt, now),
          sql`(${outbox.leaseUntil} IS NULL OR ${outbox.leaseUntil} <= ${now})`,
        ),
      )
      .orderBy(asc(outbox.nextAttemptAt))
      .limit(limit)

    if (candidates.length === 0) return []

    const ids = candidates.map((row) => row.messageId)
    return tx
      .update(outbox)
      .set({ leaseOwner: workerId, leaseUntil, status: "in_flight" })
      .where(inArray(outbox.messageId, ids))
      .returning()
  })
}

/**
 * Mark a claimed message as successfully delivered.
 */
export async function completeOutbox(db: ButlerDb, messageId: string): Promise<void> {
  await db
    .update(outbox)
    .set({ status: "delivered", deliveredAt: new Date() })
    .where(eq(outbox.messageId, messageId))
}

/**
 * Record a failed delivery attempt and schedule the next retry with
 * exponential backoff (BASE * 2^(attempt-1), capped at MAX).
 */
export async function failOutbox(db: ButlerDb, messageId: string, error: string): Promise<void> {
  const rows = await db.select().from(outbox).where(eq(outbox.messageId, messageId))
  const msg = rows[0]
  if (!msg) return
  const attempt = (msg.attemptCount ?? 0) + 1
  const backoff = Math.min(BASE_BACKOFF_MS * Math.pow(2, attempt - 1), MAX_BACKOFF_MS)
  const nextAttemptAt = new Date(Date.now() + backoff)
  await db
    .update(outbox)
    .set({
      attemptCount: attempt,
      lastError: error.slice(0, 1000),
      nextAttemptAt,
      leaseOwner: null,
      leaseUntil: null,
      status: "pending",
    })
    .where(eq(outbox.messageId, messageId))
}
