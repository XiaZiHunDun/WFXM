/**
 * Phase 5 P0: dependency diagnostics for `/healthz` and
 * `GET /v1/owner/diagnostics`.
 *
 * Aggregates DB liveness, outbox backlog, waiting approvals, last
 * successful Run and trace pipeline counters into one read-only report.
 * Kept tolerant of test wirings without `db` (legacy `createRoutes`
 * stubs) — those degrade to `status: "ok"` instead of failing.
 */
import { and, asc, desc, eq, sql } from "drizzle-orm"
import { outbox, runs, steps, type ButlerDb } from "@butler/persistence"
import {
  parseTraceConfig,
  parseTraceRetention,
  type TraceConfig,
} from "@butler/domain/observability/local-trace.js"
import { getSharedLocalTracer } from "@butler/runtime/observability/local-tracer.js"
import type { Wiring } from "./wiring.js"

export interface DiagnosticsChecks {
  readonly db: {
    readonly status: "up" | "down"
    readonly latency_ms: number
    readonly error?: string
  }
  readonly outbox: {
    readonly pending: number
    readonly failed: number
    readonly oldest_pending_age_ms: number | null
  }
  readonly approvals: { readonly waiting: number }
  readonly runs: { readonly last_succeeded_at: string | null }
  readonly traces: {
    readonly memory: number
    readonly pending_write: number
    readonly dropped: number
    readonly persisted: number | null
  }
}

export interface DiagnosticsReport {
  readonly status: "ok" | "degraded"
  readonly wiring: "v5"
  readonly checks: DiagnosticsChecks
  readonly trace: TraceConfig & {
    readonly retention_days: number
    readonly max_rows: number
  }
}

function emptyChecks(): DiagnosticsChecks {
  return {
    db: { status: "up", latency_ms: 0 },
    outbox: { pending: 0, failed: 0, oldest_pending_age_ms: null },
    approvals: { waiting: 0 },
    runs: { last_succeeded_at: null },
    traces: { memory: 0, pending_write: 0, dropped: 0, persisted: null },
  }
}

function traceBlock(env: Readonly<Record<string, string | undefined>>) {
  const config = parseTraceConfig(env)
  const retention = parseTraceRetention(env)
  return {
    enabled: config.enabled,
    redact: config.redact,
    maxEvents: config.maxEvents,
    exporter: config.exporter,
    retention_days: retention.retentionDays,
    max_rows: retention.maxRows,
  }
}

function traceCounters(persisted: number | null): DiagnosticsChecks["traces"] {
  const tracer = getSharedLocalTracer()
  const stats = tracer.stats()
  return {
    memory: tracer.size(),
    pending_write: tracer.pending(),
    dropped: stats.dropped,
    persisted,
  }
}

export async function collectDiagnostics(
  wiring: Wiring,
  env: Readonly<Record<string, string | undefined>> = process.env,
  nowMs: number = Date.now(),
): Promise<DiagnosticsReport> {
  const traceStore = wiring.traceStore ?? null
  const persisted = traceStore ? await traceStore.count().catch(() => null) : null
  const trace = traceBlock(env)

  const db = (wiring as { readonly db?: ButlerDb }).db
  if (!db) {
    // Legacy route stubs (tests) pass a wiring without a DB handle.
    return { status: "ok", wiring: "v5", checks: emptyChecks(), trace }
  }

  const started = Date.now()
  let dbUp = true
  let dbError: string | undefined
  try {
    await db.execute(sql`select 1`)
  } catch (err) {
    dbUp = false
    dbError = err instanceof Error ? err.message : String(err)
  }
  const latencyMs = Date.now() - started

  let outboxPending = 0
  let outboxFailed = 0
  let oldestPendingAgeMs: number | null = null
  let approvalsWaiting = 0
  let lastSucceededAt: string | null = null

  if (dbUp) {
    try {
      const statusRows = await db
        .select({ status: outbox.status, count: sql<number>`count(*)::int` })
        .from(outbox)
        .groupBy(outbox.status)
      for (const row of statusRows) {
        if (row.status === "pending") outboxPending = row.count
        if (row.status === "failed") outboxFailed = row.count
      }

      const oldestPending = await db
        .select({ createdAt: outbox.createdAt })
        .from(outbox)
        .where(eq(outbox.status, "pending"))
        .orderBy(asc(outbox.createdAt))
        .limit(1)
      if (oldestPending[0]) {
        oldestPendingAgeMs = Math.max(0, nowMs - oldestPending[0].createdAt.getTime())
      }

      const waitingRows = await db
        .select({ count: sql<number>`count(*)::int` })
        .from(steps)
        .where(and(eq(steps.kind, "approval"), eq(steps.status, "waiting")))
      approvalsWaiting = waitingRows[0]?.count ?? 0

      const lastSucceeded = await db
        .select({ updatedAt: runs.updatedAt })
        .from(runs)
        .where(eq(runs.status, "succeeded"))
        .orderBy(desc(runs.updatedAt))
        .limit(1)
      lastSucceededAt = lastSucceeded[0]?.updatedAt.toISOString() ?? null
    } catch (err) {
      // Aggregation failure should degrade health, not crash the probe.
      dbUp = false
      dbError = err instanceof Error ? err.message : String(err)
    }
  }

  const checks: DiagnosticsChecks = {
    db: {
      status: dbUp ? "up" : "down",
      latency_ms: latencyMs,
      ...(dbError === undefined ? {} : { error: dbError }),
    },
    outbox: {
      pending: outboxPending,
      failed: outboxFailed,
      oldest_pending_age_ms: oldestPendingAgeMs,
    },
    approvals: { waiting: approvalsWaiting },
    runs: { last_succeeded_at: lastSucceededAt },
    traces: traceCounters(persisted),
  }

  return {
    status: dbUp ? "ok" : "degraded",
    wiring: "v5",
    checks,
    trace,
  }
}
