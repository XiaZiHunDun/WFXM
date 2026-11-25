/**
 * Phase 5 P1: owner-only WeChat observability commands.
 *
 * `/诊断` (alias `/diag`) renders the same aggregate as
 * `GET /v1/owner/diagnostics`; `/日志 [n]` (alias `/logs`) lists the most
 * recent trace events. Both are read-only, owner-gated and never echo raw
 * exception text — only stable error codes and short turn ids.
 *
 * `/状态` is already taken by the project surface (`wechat-project-surface.ts`),
 * so the system diagnostics command intentionally uses a distinct name.
 */
import type { TraceEvent } from "@butler/domain/observability/local-trace.js"
import { turnIdShort } from "@butler/domain/observability/error-codes.js"
import { getSharedLocalTracer } from "@butler/runtime/observability/local-tracer.js"
import { collectDiagnostics, type DiagnosticsReport } from "./diagnostics.js"
import { parseCsvIds } from "./ilink-config.js"
import { resolveOwnerSubject } from "./tool-boundary-helpers.js"
import type { ButlerLoopResult } from "./wechat-inbound-butler.js"
import type { Wiring } from "./wiring.js"

const SHANGHAI_OFFSET_MS = 8 * 60 * 60 * 1000
const MINUTE_MS = 60 * 1000

export const DEFAULT_LOG_LINES = 10
export const MAX_LOG_LINES = 50

export type WechatObservabilityCommand =
  { readonly kind: "diagnostics" } | { readonly kind: "logs"; readonly limit: number }

function pad(n: number): string {
  return n.toString().padStart(2, "0")
}

/** `MM-DD HH:mm:ss` in Asia/Shanghai (UTC+8, no DST). */
function formatClock(ms: number): string {
  const d = new Date(ms + SHANGHAI_OFFSET_MS)
  return [
    `${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`,
    `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`,
  ].join(" ")
}

function formatAge(ms: number): string {
  if (ms < MINUTE_MS) return "不到 1 分钟"
  const minutes = Math.floor(ms / MINUTE_MS)
  if (minutes < 60) return `${minutes} 分钟`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} 小时`
  return `${Math.floor(hours / 24)} 天`
}

/**
 * `/诊断`, `/diag`, `/日志`, `/日志 20`, `/logs 5`.
 * Unknown shapes return null so the message falls through to normal intake.
 */
export function parseWechatObservabilityCommand(
  content: string,
): WechatObservabilityCommand | null {
  const trimmed = content.trim()
  if (trimmed === "/诊断" || trimmed === "/diag") return { kind: "diagnostics" }
  const match = /^\/(?:日志|logs)(?:\s+(\S+))?$/.exec(trimmed)
  if (!match) return null
  const raw = match[1]
  const parsed = raw === undefined ? DEFAULT_LOG_LINES : Number.parseInt(raw, 10)
  const limit =
    Number.isFinite(parsed) && parsed > 0 ? Math.min(parsed, MAX_LOG_LINES) : DEFAULT_LOG_LINES
  return { kind: "logs", limit }
}

/**
 * Fail-closed owner gate: requires `BUTLER_OWNER_WECHAT_ID` to be configured
 * and to contain the sender. Non-owners fall through to normal intake rather
 * than getting a reply that confirms the command exists.
 */
export function isWechatObservabilityOwner(fromUserId: string, env: NodeJS.ProcessEnv): boolean {
  const id = fromUserId.trim()
  if (!id) return false
  const owner = resolveOwnerSubject(env, "")
  if (owner !== "" && owner === id) return true
  return parseCsvIds(env["BUTLER_OWNER_WECHAT_ID"]).includes(id)
}

function done(reply: string, traces: readonly string[]): ButlerLoopResult {
  return {
    reply,
    iterations: 0,
    toolCalls: 0,
    finalDecision: "Respond",
    traces: [...traces],
  }
}

export function formatDiagnosticsReply(report: DiagnosticsReport): string {
  const checks = report.checks
  const lastSucceeded = checks.runs.last_succeeded_at
    ? formatClock(Date.parse(checks.runs.last_succeeded_at))
    : "—"
  const lines = [
    `【系统诊断】${report.status === "ok" ? "正常" : "降级"}`,
    `数据库：${checks.db.status === "up" ? `正常（${checks.db.latency_ms}ms）` : "异常"}`,
    `待发消息：${checks.outbox.pending} 条（失败 ${checks.outbox.failed}）`,
    `待审批：${checks.approvals.waiting} 条`,
    `最近成功运行：${lastSucceeded}`,
    `轨迹：内存 ${checks.traces.memory} · 待写 ${checks.traces.pending_write} · 已存 ${
      checks.traces.persisted ?? "?"
    }`,
  ]
  if (checks.outbox.pending > 0 && checks.outbox.oldest_pending_age_ms !== null) {
    lines.push(`最久待发：${formatAge(checks.outbox.oldest_pending_age_ms)}`)
  }
  lines.push(`保留：${report.trace.retention_days} 天 / ${report.trace.max_rows} 条`)
  if (!report.trace.enabled) lines.push("轨迹总开关：已关闭")
  return lines.join("\n")
}

function traceErrorCode(event: TraceEvent): string | null {
  const raw = event.detail["code"]
  return typeof raw === "string" && raw.length > 0 ? raw : null
}

function formatTraceLine(event: TraceEvent): string {
  const parts = [formatClock(event.createdAt), `${event.kind}/${event.name}`, event.status]
  const short = turnIdShort(event.turnId)
  if (short !== "") parts.push(`[${short}]`)
  const code = traceErrorCode(event)
  if (code !== null) parts.push(code)
  if (event.durationMs !== null && event.durationMs >= 1000) {
    parts.push(`${(event.durationMs / 1000).toFixed(1)}s`)
  }
  return `· ${parts.join(" ")}`
}

export function formatTraceLogReply(
  events: readonly TraceEvent[],
  opts: { readonly source: "store" | "memory" | "none"; readonly limit: number },
): string {
  if (opts.source === "none") return "轨迹功能未启用（BUTLER_V5_TRACE=0），看不到日志。"
  if (events.length === 0) return "暂无轨迹记录。"
  const visible = events.slice(-opts.limit)
  return [`最近 ${visible.length} 条轨迹：`, ...visible.map(formatTraceLine)].join("\n")
}

async function readRecentTraces(
  wiring: Wiring,
  limit: number,
): Promise<{
  readonly events: readonly TraceEvent[]
  readonly source: "store" | "memory" | "none"
}> {
  if (wiring.traceStore) {
    const events = await wiring.traceStore.list({ limit }).catch(() => null)
    if (events !== null) return { events, source: "store" }
  }
  const tracer = getSharedLocalTracer()
  if (!tracer.config.enabled) return { events: [], source: "none" }
  return { events: tracer.list({ limit }), source: "memory" }
}

export async function tryWechatObservabilityCommand(args: {
  readonly wiring: Wiring
  readonly fromUserId: string
  readonly content: string
  readonly env?: NodeJS.ProcessEnv
}): Promise<ButlerLoopResult | null> {
  const command = parseWechatObservabilityCommand(args.content)
  if (!command) return null
  const env = args.env ?? process.env
  if (!isWechatObservabilityOwner(args.fromUserId, env)) return null

  if (command.kind === "diagnostics") {
    const report = await collectDiagnostics(args.wiring, env)
    return done(formatDiagnosticsReply(report), [`wechat-diag: ${report.status}`])
  }

  const { events, source } = await readRecentTraces(args.wiring, command.limit)
  return done(formatTraceLogReply(events, { source, limit: command.limit }), [
    `wechat-logs: ${source} ${events.length}`,
  ])
}
