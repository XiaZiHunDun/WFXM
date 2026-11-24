import { and, asc, desc, eq, inArray, lt, sql } from "drizzle-orm"
import type { TraceEvent, TraceKind } from "@butler/domain/observability/local-trace.js"
import type { ButlerDb } from "./db.js"
import { traceEvents } from "./schema.js"

export interface TraceListFilter {
  readonly runId?: string
  readonly conversationId?: string
  readonly turnId?: string
  readonly kind?: TraceKind
  readonly limit?: number
}

export interface TracePruneResult {
  readonly deletedByAge: number
  readonly deletedByRows: number
}

export interface TraceStore {
  readonly append: (events: readonly TraceEvent[]) => Promise<void>
  readonly list: (filter?: TraceListFilter) => Promise<readonly TraceEvent[]>
  readonly count: () => Promise<number>
  readonly oldestCreatedAt: () => Promise<Date | null>
  /**
   * Delete rows older than `retentionDays`, then evict the oldest rows
   * until at most `maxRows` remain. Safe to call on an empty table.
   */
  readonly prune: (input: {
    readonly retentionDays: number
    readonly maxRows: number
    readonly nowMs?: number
  }) => Promise<TracePruneResult>
}

const DAY_MS = 24 * 60 * 60 * 1000

function toRow(event: TraceEvent): typeof traceEvents.$inferInsert {
  return {
    id: event.id,
    kind: event.kind,
    name: event.name,
    status: event.status,
    turnId: event.turnId,
    conversationId: event.conversationId,
    runId: event.runId,
    stepId: event.stepId,
    parentRunId: event.parentRunId,
    subject: event.subject,
    triggerSource: event.triggerSource,
    capability: event.capability,
    policyDecision: event.policyDecision,
    grantId: event.grantId,
    waitingStepId: event.waitingStepId,
    durationMs: event.durationMs,
    tokenInput: event.token?.inputTokens ?? null,
    tokenOutput: event.token?.outputTokens ?? null,
    tokenTotal: event.token?.totalTokens ?? null,
    costUsd: event.costUsd,
    detail: event.detail as Record<string, unknown>,
    createdAt: new Date(event.createdAt),
  }
}

function toEvent(row: typeof traceEvents.$inferSelect): TraceEvent {
  return {
    id: row.id,
    kind: row.kind as TraceKind,
    name: row.name,
    status: row.status as TraceEvent["status"],
    turnId: row.turnId,
    conversationId: row.conversationId,
    runId: row.runId,
    stepId: row.stepId,
    parentRunId: row.parentRunId,
    subject: row.subject,
    triggerSource: row.triggerSource,
    capability: row.capability,
    policyDecision: row.policyDecision,
    grantId: row.grantId,
    waitingStepId: row.waitingStepId,
    durationMs: row.durationMs,
    token:
      row.tokenInput !== null && row.tokenOutput !== null && row.tokenTotal !== null
        ? {
            inputTokens: row.tokenInput,
            outputTokens: row.tokenOutput,
            totalTokens: row.tokenTotal,
          }
        : null,
    costUsd: row.costUsd,
    detail: (row.detail ?? {}) as Readonly<Record<string, unknown>>,
    createdAt: row.createdAt.getTime(),
  }
}

export function createTraceStore(db: ButlerDb): TraceStore {
  const countRows = async (): Promise<number> => {
    const rows = await db.select({ count: sql<number>`count(*)::int` }).from(traceEvents)
    return rows[0]?.count ?? 0
  }

  return {
    async append(events) {
      if (events.length === 0) return
      await db.insert(traceEvents).values(events.map(toRow))
    },

    async list(filter = {}) {
      const limit = filter.limit ?? 100
      if (limit <= 0) return []
      const conditions = [
        filter.runId ? eq(traceEvents.runId, filter.runId) : undefined,
        filter.conversationId ? eq(traceEvents.conversationId, filter.conversationId) : undefined,
        filter.turnId ? eq(traceEvents.turnId, filter.turnId) : undefined,
        filter.kind ? eq(traceEvents.kind, filter.kind) : undefined,
      ].filter((value): value is NonNullable<typeof value> => value !== undefined)
      const rows = await db
        .select()
        .from(traceEvents)
        .where(conditions.length === 0 ? undefined : and(...conditions))
        .orderBy(desc(traceEvents.createdAt))
        .limit(limit)
      return rows.reverse().map(toEvent)
    },

    count() {
      return countRows()
    },

    async oldestCreatedAt() {
      const rows = await db
        .select({ createdAt: traceEvents.createdAt })
        .from(traceEvents)
        .orderBy(asc(traceEvents.createdAt))
        .limit(1)
      return rows[0]?.createdAt ?? null
    },

    async prune(input) {
      const nowMs = input.nowMs ?? Date.now()
      const cutoff = new Date(nowMs - input.retentionDays * DAY_MS)
      const aged = await db.delete(traceEvents).where(lt(traceEvents.createdAt, cutoff)).returning()

      let deletedByRows = 0
      if (input.maxRows > 0) {
        const total = await countRows()
        const excess = total - input.maxRows
        if (excess > 0) {
          const oldest = await db
            .select({ id: traceEvents.id })
            .from(traceEvents)
            .orderBy(asc(traceEvents.createdAt))
            .limit(excess)
          if (oldest.length > 0) {
            await db.delete(traceEvents).where(
              inArray(
                traceEvents.id,
                oldest.map((row) => row.id),
              ),
            )
            deletedByRows = oldest.length
          }
        }
      }
      return { deletedByAge: aged.length, deletedByRows }
    },
  }
}
