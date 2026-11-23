/**
 * `/周报` (alias `/weekly`) — manual, LLM-free weekly digest.
 * Reuses the exact same collector + renderer as the scheduled push.
 */
import { formatReminderTime } from "./reminder-time.js"
import type { ButlerLoopResult } from "./wechat-inbound-butler.js"
import {
  collectWeeklyDigest,
  recordWeeklyDigestAudit,
  renderEmptyWeeklyDigest,
  renderWeeklyDigest,
  type TraceReader,
} from "./weekly-digest.js"
import type { Wiring } from "./wiring.js"

function done(reply: string, traces: readonly string[]): ButlerLoopResult {
  return {
    reply,
    iterations: 0,
    toolCalls: 0,
    finalDecision: "Respond",
    traces: [...traces],
  }
}

function describeError(err: unknown): string {
  const raw = err instanceof Error ? err.message : String(err)
  const text = raw.trim()
  if (!text) return "未知错误"
  return text.length > 200 ? `${text.slice(0, 200)}…` : text
}

export async function tryWechatWeeklyDigestCommand(args: {
  readonly wiring: Wiring
  readonly fromUserId: string
  readonly content: string
  readonly env?: NodeJS.ProcessEnv
  readonly nowMs?: () => number
  readonly tracer?: TraceReader
}): Promise<ButlerLoopResult | null> {
  const trimmed = args.content.trim()
  if (trimmed !== "/周报" && trimmed !== "/weekly") return null

  const env = args.env ?? process.env
  const subject = args.fromUserId.trim()
  const nowMs = args.nowMs?.() ?? Date.now()
  const dayKey = formatReminderTime(nowMs).slice(0, 10)

  try {
    const data = await collectWeeklyDigest({
      wiring: args.wiring,
      subject,
      nowMs,
      env,
      ...(args.tracer === undefined ? {} : { tracer: args.tracer }),
    })
    if (!data.hasData) {
      return done(renderEmptyWeeklyDigest(data), ["weekly-digest: empty"])
    }
    return done(renderWeeklyDigest(data), [
      `weekly-digest: done=${data.completedTasks} open=${data.openTasks} failed=${data.failedRuns} approvals=${data.approvals}`,
    ])
  } catch (err) {
    const reason = describeError(err)
    await recordWeeklyDigestAudit({
      wiring: args.wiring,
      action: "weekly_digest.failed",
      subject: subject || "owner",
      detail: { dayKey, reason },
      nowMs,
    })
    return done(`周报生成失败：${reason}`, [`weekly-digest: error ${reason}`])
  }
}
