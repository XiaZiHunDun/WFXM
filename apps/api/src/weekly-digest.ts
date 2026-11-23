/**
 * Weekly digest — deterministic, read-only aggregation for `/周报` and the
 * opt-in Monday push. No LLM, no state changes.
 *
 * Data sources (kept in lockstep with existing owner surfaces):
 *   - completed / open tasks: TaskStore (same as `/待办` and /v1/owner/tasks)
 *   - failed runs: local tracer `run_failed` events (same as /v1/owner/usage)
 *   - approvals: audit_events `approval.requested` (same as owner audit trail)
 */
import type { TraceEvent } from "@butler/domain/observability/local-trace.js"
import { getSharedLocalTracer } from "@butler/runtime/observability/local-tracer.js"
import { formatReminderTime } from "./reminder-time.js"
import type { Wiring } from "./wiring.js"

const DAY_MS = 24 * 60 * 60 * 1000

/** Digest window covers the trailing 7 days, matching "上周". */
export const WEEKLY_DIGEST_WINDOW_MS = 7 * DAY_MS
/** Audit lookback for same-day dedupe; one day of slack for timezone edges. */
const DIGEST_DEDUPE_WINDOW_MS = 8 * DAY_MS

export interface WeeklyDigestStats {
  readonly completedTasks: number
  readonly openTasks: number
  readonly failedRuns: number
  readonly approvals: number
}

export interface WeeklyDigestData extends WeeklyDigestStats {
  readonly windowStartMs: number
  readonly windowEndMs: number
  /** False when every counter is zero — auto push stays quiet. */
  readonly hasData: boolean
}

/** Minimal tracer surface so tests can inject a fake reader. */
export interface TraceReader {
  readonly list: (filter?: {
    readonly runId?: string
    readonly conversationId?: string
    readonly kind?: TraceEvent["kind"]
    readonly limit?: number
  }) => readonly TraceEvent[]
}

export async function collectWeeklyDigest(args: {
  readonly wiring: Wiring
  readonly subject: string
  readonly nowMs: number
  readonly windowMs?: number
  readonly env?: NodeJS.ProcessEnv
  readonly tracer?: TraceReader
}): Promise<WeeklyDigestData> {
  const subject = args.subject.trim()
  if (!subject) throw new Error("缺少统计对象")

  const store = args.wiring.taskStore
  if (!store) throw new Error("任务存储暂不可用")

  const windowMs = args.windowMs ?? WEEKLY_DIGEST_WINDOW_MS
  const windowEndMs = args.nowMs
  const windowStartMs = windowEndMs - windowMs

  const tasks = await store.listBySubject({ subject, limit: 500 })
  const completedTasks = tasks.filter(
    (task) =>
      task.status === "done" && task.updatedAt >= windowStartMs && task.updatedAt <= windowEndMs,
  ).length
  const openTasks = tasks.filter((task) => task.status === "open").length

  const tracer = args.tracer ?? getSharedLocalTracer(args.env ?? process.env)
  const failedRuns = tracer
    .list({ limit: 5000 })
    .filter(
      (event) =>
        event.kind === "step" &&
        event.name === "run_failed" &&
        event.createdAt >= windowStartMs &&
        event.createdAt <= windowEndMs,
    ).length

  const audits = await args.wiring.runtimeStore.listRecentAuditEvents({
    windowMs,
    limit: 1000,
  })
  const approvals = audits.filter(
    (event) =>
      event.action === "approval.requested" &&
      event.createdAt.getTime() >= windowStartMs &&
      event.createdAt.getTime() <= windowEndMs,
  ).length

  return {
    completedTasks,
    openTasks,
    failedRuns,
    approvals,
    windowStartMs,
    windowEndMs,
    hasData: completedTasks + openTasks + failedRuns + approvals > 0,
  }
}

/** `MM-DD` in Asia/Shanghai (no DST). */
function monthDay(ms: number): string {
  return formatReminderTime(ms).slice(5, 10)
}

/** Shared renderer for both the slash command and the scheduled push. */
export function renderWeeklyDigest(data: WeeklyDigestData): string {
  return [
    `【周报】${monthDay(data.windowStartMs)} ~ ${monthDay(data.windowEndMs)}`,
    `完成 ${data.completedTasks} 项`,
    `待办 ${data.openTasks} 项`,
    `失败 ${data.failedRuns} 次`,
    `审批 ${data.approvals} 次`,
  ].join("\n")
}

/** Owner-facing reply when the trailing week has nothing to report. */
export function renderEmptyWeeklyDigest(data: WeeklyDigestData): string {
  return `【周报】${monthDay(data.windowStartMs)} ~ ${monthDay(data.windowEndMs)}\n过去 7 天没有可汇总的记录。`
}

export interface WeeklyDigestAuditInput {
  readonly wiring: Wiring
  readonly action: "weekly_digest.sent" | "weekly_digest.failed"
  readonly subject: string
  readonly detail: Readonly<Record<string, unknown>>
  readonly nowMs: number
}

/** Best-effort audit write; never breaks the digest reply / push. */
export async function recordWeeklyDigestAudit(args: WeeklyDigestAuditInput): Promise<void> {
  try {
    await args.wiring.runtimeStore.appendAuditEvent({
      auditId: crypto.randomUUID(),
      runId: null,
      conversationId: null,
      correlationId: null,
      action: args.action,
      actor: "owner-direct",
      subject: args.subject,
      detail: args.detail,
      createdAt: new Date(args.nowMs),
    })
  } catch (err) {
    // eslint-disable-next-line no-console -- operator log when no logger injected
    console.error(`[weekly-digest] appendAuditEvent (${args.action}) failed:`, err)
  }
}

/**
 * True when the same owner already received a digest for `dayKey` in the last
 * 8 days. Makes the scheduled push idempotent across ticks and restarts.
 */
export async function hasWeeklyDigestSentForDay(args: {
  readonly wiring: Wiring
  readonly subject: string
  readonly dayKey: string
}): Promise<boolean> {
  const audits = await args.wiring.runtimeStore.listRecentAuditEvents({
    windowMs: DIGEST_DEDUPE_WINDOW_MS,
    limit: 1000,
  })
  return audits.some(
    (event) =>
      event.action === "weekly_digest.sent" &&
      event.subject === args.subject &&
      event.detail["dayKey"] === args.dayKey,
  )
}
