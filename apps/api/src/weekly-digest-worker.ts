/**
 * Weekly digest worker — pushes one deterministic summary per week.
 *
 * Opt-in via BUTLER_V5_WEEKLY_DIGEST_ENABLED=1. Read-only: it queries tasks,
 * run traces and audit events, never runs tools or the LLM.
 */
import type { ChannelKind, ChannelPort } from "@butler/ports/core/channel.js"
import { parseWeeklyDigestConfig, type WeeklyDigestConfig } from "./weekly-digest-config.js"
import {
  collectWeeklyDigest,
  hasWeeklyDigestSentForDay,
  recordWeeklyDigestAudit,
  renderWeeklyDigest,
  type TraceReader,
  type WeeklyDigestData,
} from "./weekly-digest.js"
import { formatReminderTime } from "./reminder-time.js"
import { sendWechatText } from "./wechat-run-notify.js"
import type { Wiring } from "./wiring.js"

const SHANGHAI_OFFSET_MS = 8 * 60 * 60 * 1000
/** Ticks landing within this window after the configured time may fire. */
const FIRE_WINDOW_MINUTES = 10

export type WeeklyDigestWorkerLogger = {
  readonly info: (msg: string, ...args: unknown[]) => void
  readonly warn: (msg: string, ...args: unknown[]) => void
  readonly error: (msg: string, ...args: unknown[]) => void
}

const defaultLogger: WeeklyDigestWorkerLogger = {
  info: (msg, ...args) => {
    // eslint-disable-next-line no-console -- operator log
    console.info(msg, ...args)
  },
  warn: (msg, ...args) => {
    // eslint-disable-next-line no-console -- operator log
    console.warn(msg, ...args)
  },
  error: (msg, ...args) => {
    // eslint-disable-next-line no-console -- operator log
    console.error(msg, ...args)
  },
}

export type WeeklyDigestSendResult =
  { readonly ok: true } | { readonly ok: false; readonly reason: string }

export type WeeklyDigestSender = (args: {
  readonly to: string
  readonly text: string
  readonly env: NodeJS.ProcessEnv
  readonly channels?: ReadonlyMap<ChannelKind, ChannelPort>
}) => Promise<WeeklyDigestSendResult>

export type WeeklyDigestTickResult =
  | { readonly sent: true; readonly text: string; readonly data: WeeklyDigestData }
  | { readonly sent: false; readonly reason: string; readonly text?: string }

interface ShanghaiClock {
  readonly dayKey: string
  readonly weekday: number
  readonly minutes: number
}

/** Wall clock in Asia/Shanghai (UTC+8, no DST). */
function shanghaiClock(nowMs: number): ShanghaiClock {
  const local = formatReminderTime(nowMs)
  const parts = local.slice(11).split(":")
  const hour = Number(parts[0] ?? 0)
  const minute = Number(parts[1] ?? 0)
  return {
    dayKey: local.slice(0, 10),
    weekday: new Date(nowMs + SHANGHAI_OFFSET_MS).getUTCDay(),
    minutes: hour * 60 + minute,
  }
}

export function isWithinWeeklyDigestWindow(config: WeeklyDigestConfig, nowMs: number): boolean {
  const clock = shanghaiClock(nowMs)
  if (clock.weekday !== config.weekday) return false
  const scheduled = config.hour * 60 + config.minute
  return clock.minutes >= scheduled && clock.minutes < scheduled + FIRE_WINDOW_MINUTES
}

/** Evaluate the weekly push once. Exported for tests. */
export async function runWeeklyDigestTick(args: {
  readonly wiring: Wiring
  readonly config?: WeeklyDigestConfig
  readonly env?: NodeJS.ProcessEnv
  readonly nowMs?: () => number
  readonly send?: WeeklyDigestSender
  readonly tracer?: TraceReader
  readonly logger?: WeeklyDigestWorkerLogger
}): Promise<WeeklyDigestTickResult> {
  const env = args.env ?? process.env
  const config = args.config ?? parseWeeklyDigestConfig(env)
  const logger = args.logger ?? defaultLogger
  if (!config.enabled) return { sent: false, reason: "disabled" }

  const to = config.to?.trim() ?? ""
  if (!to) return { sent: false, reason: "no_owner" }

  const nowMs = args.nowMs?.() ?? Date.now()
  if (!isWithinWeeklyDigestWindow(config, nowMs)) {
    return { sent: false, reason: "not_scheduled" }
  }

  const dayKey = shanghaiClock(nowMs).dayKey
  if (await hasWeeklyDigestSentForDay({ wiring: args.wiring, subject: to, dayKey })) {
    return { sent: false, reason: "already_sent" }
  }

  let data: WeeklyDigestData
  try {
    data = await collectWeeklyDigest({
      wiring: args.wiring,
      subject: to,
      nowMs,
      env,
      ...(args.tracer === undefined ? {} : { tracer: args.tracer }),
    })
  } catch (err) {
    const reason = err instanceof Error ? err.message : String(err)
    await recordWeeklyDigestAudit({
      wiring: args.wiring,
      action: "weekly_digest.failed",
      subject: to,
      detail: { dayKey, reason },
      nowMs,
    })
    logger.warn(`[weekly-digest] collect failed: ${reason}`)
    return { sent: false, reason: "error", text: `周报生成失败：${reason}` }
  }

  if (!data.hasData) {
    logger.info(`[weekly-digest] quiet week day=${dayKey}; nothing to send`)
    return { sent: false, reason: "empty" }
  }

  const text = renderWeeklyDigest(data)
  const send = args.send ?? sendWechatText
  const result = await send({
    to,
    text,
    env,
    ...(args.wiring.channels.size === 0 ? {} : { channels: args.wiring.channels }),
  })
  if (!result.ok) {
    await recordWeeklyDigestAudit({
      wiring: args.wiring,
      action: "weekly_digest.failed",
      subject: to,
      detail: { dayKey, reason: result.reason, stage: "send" },
      nowMs,
    })
    logger.warn(`[weekly-digest] send failed day=${dayKey}: ${result.reason}`)
    return { sent: false, reason: "send_failed", text }
  }

  await recordWeeklyDigestAudit({
    wiring: args.wiring,
    action: "weekly_digest.sent",
    subject: to,
    detail: {
      dayKey,
      completedTasks: data.completedTasks,
      openTasks: data.openTasks,
      failedRuns: data.failedRuns,
      approvals: data.approvals,
    },
    nowMs,
  })
  logger.info(`[weekly-digest] sent day=${dayKey}`)
  return { sent: true, text, data }
}

export interface WeeklyDigestWorkerHandle {
  readonly stop: () => void
}

/** Start the opt-in weekly digest poller. No-op when disabled or no recipient. */
export function startWeeklyDigestWorkerIfEnabled(args: {
  readonly wiring: Wiring
  readonly env?: NodeJS.ProcessEnv
  readonly config?: WeeklyDigestConfig
  readonly logger?: WeeklyDigestWorkerLogger
}): WeeklyDigestWorkerHandle | null {
  const env = args.env ?? process.env
  const config = args.config ?? parseWeeklyDigestConfig(env)
  const logger = args.logger ?? defaultLogger
  if (!config.enabled) return null
  if (!config.to) {
    logger.warn(
      "[weekly-digest] enabled but BUTLER_V5_WEEKLY_DIGEST_TO is unset; worker not started",
    )
    return null
  }

  let stopped = false
  let timer: ReturnType<typeof setTimeout> | null = null

  const tick = async (): Promise<void> => {
    if (stopped) return
    try {
      await runWeeklyDigestTick({ wiring: args.wiring, env, config, logger })
    } catch (err) {
      logger.error("[weekly-digest] tick failed:", err instanceof Error ? err.message : String(err))
    }
    if (stopped) return
    timer = setTimeout(() => {
      void tick()
    }, config.tickMs)
  }

  logger.info(
    `[weekly-digest] worker started weekday=${config.weekday} time=${config.hour}:${String(config.minute).padStart(2, "0")} tickMs=${config.tickMs}`,
  )
  void tick()

  return {
    stop: () => {
      stopped = true
      if (timer) clearTimeout(timer)
      timer = null
    },
  }
}
