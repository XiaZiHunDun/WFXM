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
import { clusterFailures, type FailureSummary } from "./failure-clusters.js"
import { readEvalBaseline, type EvalBaselineStatus } from "./eval-baseline.js"
import type { Wiring } from "./wiring.js"

const DAY_MS = 24 * 60 * 60 * 1000
/** Failure clustering window: same trailing week as the digest. */
export const DIAGNOSTICS_FAILURE_WINDOW_MS = 7 * DAY_MS

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
  /** Phase 6 P1: failures in the trailing week, grouped by `code × tool`. */
  readonly failures: {
    readonly window_ms: number
    readonly total: number
    readonly clusters: FailureSummary["clusters"]
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
  /** Phase 6 P1: age of the real-LLM regression baseline. */
  readonly eval_baseline: EvalBaselineStatus
}

function emptyChecks(): DiagnosticsChecks {
  return {
    db: { status: "up", latency_ms: 0 },
    outbox: { pending: 0, failed: 0, oldest_pending_age_ms: null },
    approvals: { waiting: 0 },
    runs: { last_succeeded_at: null },
    traces: { memory: 0, pending_write: 0, dropped: 0, persisted: null },
    failures: { window_ms: DIAGNOSTICS_FAILURE_WINDOW_MS, total: 0, clusters: [] },
  }
}

/**
 * Phase 6 P1: read the trailing week's trace rows and cluster failures.
 * Prefers the persisted store (consistent with `/日志` + `/周报`); the
 * in-process ring buffer is the fallback for wirings without one.
 */
async function collectFailures(
  wiring: Wiring,
  env: Readonly<Record<string, string | undefined>>,
  nowMs: number,
): Promise<DiagnosticsChecks["failures"]> {
  const sinceMs = nowMs - DIAGNOSTICS_FAILURE_WINDOW_MS
  const observed = wiring.traceStore
    ? await wiring.traceStore.list({ sinceMs, untilMs: nowMs, limit: 5000 }).catch(() => null)
    : null
  const events =
    observed ??
    getSharedLocalTracer(env)
      .list({ limit: 5000 })
      .filter((event) => event.createdAt >= sinceMs && event.createdAt <= nowMs)
  const summary = clusterFailures(events)
  return {
    window_ms: DIAGNOSTICS_FAILURE_WINDOW_MS,
    total: summary.total,
    clusters: summary.clusters,
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
  const failures = await collectFailures(wiring, env, nowMs)
  const evalBaseline = await readEvalBaseline(env, nowMs)

  const db = (wiring as { readonly db?: ButlerDb }).db
  if (!db) {
    // Legacy route stubs (tests) pass a wiring without a DB handle.
    return {
      status: "ok",
      wiring: "v5",
      checks: { ...emptyChecks(), failures },
      trace,
      eval_baseline: evalBaseline,
    }
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
    failures,
  }

  return {
    status: dbUp ? "ok" : "degraded",
    wiring: "v5",
    checks,
    trace,
    eval_baseline: evalBaseline,
  }
}
