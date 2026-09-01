import { and, desc, eq, inArray, sql } from "drizzle-orm"
import type {
  DurableMemoryProvenance,
  DurableMemoryRecord,
  DurableMemorySourceKind,
  DurableMemoryStatus,
} from "@butler/domain/knowledge/durable-memory.js"
import type { ButlerDb } from "./db.js"
import { durableMemories } from "./schema.js"

export interface DurableMemoryStore {
  readonly create: (record: DurableMemoryRecord) => Promise<DurableMemoryRecord>
  readonly get: (memoryId: string) => Promise<DurableMemoryRecord | null>
  readonly update: (record: DurableMemoryRecord) => Promise<DurableMemoryRecord>
  readonly delete: (memoryId: string) => Promise<boolean>
  readonly listBySubject: (input: {
    readonly subject: string
    readonly status?: DurableMemoryStatus
    readonly limit?: number
    readonly offset?: number
  }) => Promise<readonly DurableMemoryRecord[]>
  readonly countBySubject: (input: {
    readonly subject: string
    readonly status?: DurableMemoryStatus
  }) => Promise<number>
  /** G1: list candidates older than threshold (for expires cleanup). */
  readonly listExpiredCandidates: (input: {
    readonly olderThanMs: number
    readonly limit?: number
  }) => Promise<readonly { id: string; createdAt: Date }[]>
  /** G1: batch mark status='expired'; idempotent (no-op if not status='candidate'). */
  readonly markExpired: (
    ids: readonly string[],
  ) => Promise<readonly { id: string; updated: boolean }[]>
  /** G2: load recent memories for dedup candidate comparison (90d window by default). */
  readonly findCandidatesForDedup: (input: {
    readonly subject: string
    readonly statuses: readonly DurableMemoryStatus[]
    readonly recentMs: number
    readonly limit: number
  }) => Promise<readonly { id: string; content: string; status: DurableMemoryStatus }[]>
  /** Soft cascade helper when a source message is deleted. */
  readonly deleteBySourceMessageId: (messageId: string) => Promise<number>
  /** Cascade when a source document is deleted. */
  readonly deleteBySourceDocumentId: (documentId: string) => Promise<number>
}

function toRecord(row: typeof durableMemories.$inferSelect): DurableMemoryRecord {
  return {
    id: row.memoryId,
    subject: row.subject,
    content: row.content,
    sourceKind: row.sourceKind as DurableMemorySourceKind,
    status: row.status as DurableMemoryStatus,
    confidence: row.confidence,
    provenance: (row.provenance ?? {}) as DurableMemoryProvenance,
    expiresAt: row.expiresAt ? row.expiresAt.getTime() : null,
    createdAt: row.createdAt.getTime(),
    updatedAt: row.updatedAt.getTime(),
    confirmedAt: row.confirmedAt ? row.confirmedAt.getTime() : null,
  }
}

export function createDurableMemoryStore(db: ButlerDb): DurableMemoryStore {
  return {
    async create(record) {
      await db.insert(durableMemories).values({
        memoryId: record.id,
        subject: record.subject,
        content: record.content,
        sourceKind: record.sourceKind,
        status: record.status,
        confidence: record.confidence,
        provenance: record.provenance,
        expiresAt: record.expiresAt !== null ? new Date(record.expiresAt) : null,
        createdAt: new Date(record.createdAt),
        updatedAt: new Date(record.updatedAt),
        confirmedAt: record.confirmedAt !== null ? new Date(record.confirmedAt) : null,
      })
      return record
    },

    async get(memoryId) {
      const rows = await db
        .select()
        .from(durableMemories)
        .where(eq(durableMemories.memoryId, memoryId))
        .limit(1)
      const row = rows[0]
      return row ? toRecord(row) : null
    },

    async update(record) {
      await db
        .update(durableMemories)
        .set({
          content: record.content,
          status: record.status,
          confidence: record.confidence,
          provenance: record.provenance,
          expiresAt: record.expiresAt !== null ? new Date(record.expiresAt) : null,
          updatedAt: new Date(record.updatedAt),
          confirmedAt: record.confirmedAt !== null ? new Date(record.confirmedAt) : null,
        })
        .where(eq(durableMemories.memoryId, record.id))
      return record
    },

    async delete(memoryId) {
      const deleted = await db
        .delete(durableMemories)
        .where(eq(durableMemories.memoryId, memoryId))
        .returning()
      return deleted.length > 0
    },

    async listBySubject(input) {
      const limit = input.limit ?? 50
      const offset = input.offset ?? 0
      const rows = input.status
        ? await db
            .select()
            .from(durableMemories)
            .where(
              and(
                eq(durableMemories.subject, input.subject),
                eq(durableMemories.status, input.status),
              ),
            )
            .orderBy(desc(durableMemories.updatedAt))
            .limit(limit)
            .offset(offset)
        : await db
            .select()
            .from(durableMemories)
            .where(eq(durableMemories.subject, input.subject))
            .orderBy(desc(durableMemories.updatedAt))
            .limit(limit)
            .offset(offset)
      return rows.map(toRecord)
    },

    async countBySubject(input) {
      const rows = input.status
        ? await db
            .select({ count: sql<number>`count(*)::int` })
            .from(durableMemories)
            .where(
              and(
                eq(durableMemories.subject, input.subject),
                eq(durableMemories.status, input.status),
              ),
            )
        : await db
            .select({ count: sql<number>`count(*)::int` })
            .from(durableMemories)
            .where(eq(durableMemories.subject, input.subject))
      return rows[0]?.count ?? 0
    },

    async listExpiredCandidates(input) {
      const limit = input.limit ?? 1000
      const rows = await db
        .select({
          memoryId: durableMemories.memoryId,
          createdAt: durableMemories.createdAt,
        })
        .from(durableMemories)
        .where(
          and(
            eq(durableMemories.status, "candidate"),
            sql`${durableMemories.createdAt} < to_timestamp(${input.olderThanMs} / 1000.0)`,
          ),
        )
        .orderBy(durableMemories.createdAt)
        .limit(limit)
      return rows.map((r) => ({ id: r.memoryId, createdAt: r.createdAt }))
    },

    async markExpired(ids) {
      const results: { id: string; updated: boolean }[] = []
      for (const id of ids) {
        const updated = await db
          .update(durableMemories)
          .set({ status: "expired", updatedAt: sql`NOW()` })
          .where(
            and(
              eq(durableMemories.memoryId, id),
              eq(durableMemories.status, "candidate"),
            ),
          )
          .returning()
        results.push({ id, updated: updated.length > 0 })
      }
      return results
    },

    async findCandidatesForDedup(input) {
      const rows = await db
        .select({
          memoryId: durableMemories.memoryId,
          content: durableMemories.content,
          status: durableMemories.status,
        })
        .from(durableMemories)
        .where(
          and(
            eq(durableMemories.subject, input.subject),
            inArray(durableMemories.status, [...input.statuses]),
            sql`${durableMemories.createdAt} > NOW() - (${input.recentMs} * INTERVAL '1 millisecond')`,
          ),
        )
        .orderBy(desc(durableMemories.createdAt))
        .limit(input.limit)
      return rows.map((r) => ({
        id: r.memoryId,
        content: r.content,
        status: r.status as DurableMemoryStatus,
      }))
    },

    async deleteBySourceMessageId(messageId) {
      const deleted = await db
        .delete(durableMemories)
        .where(sql`${durableMemories.provenance}->>'messageId' = ${messageId}`)
        .returning()
      return deleted.length
    },

    async deleteBySourceDocumentId(documentId) {
      const deleted = await db
        .delete(durableMemories)
        .where(sql`${durableMemories.provenance}->>'documentId' = ${documentId}`)
        .returning()
      return deleted.length
    },
  }
}
