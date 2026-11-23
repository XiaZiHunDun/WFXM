/**
 * Reminder worker — pushes due reminders as plain WeChat text.
 *
 * Opt-in via BUTLER_V5_REMINDERS_ENABLED=1. It never runs tools, never calls
 * the LLM, and reuses the existing outbox / ChannelPort delivery path.
 */
import type { RuntimeStore } from "@butler/domain/runtime.js"
import type { ReminderRecord } from "@butler/persistence"
import type { ChannelKind, ChannelPort } from "@butler/ports/core/channel.js"
import { parseReminderConfig, type ReminderConfig } from "./reminder-config.js"
import { formatReminderTime, nextReminderFireAtMs } from "./reminder-time.js"
import { sendWechatText } from "./wechat-run-notify.js"
import type { Wiring } from "./wiring.js"

const RETRY_COOLDOWN_MS = 60_000
const LATE_THRESHOLD_MS = 5 * 60_000

export type ReminderWorkerLogger = {
  readonly info: (msg: string, ...args: unknown[]) => void
  readonly warn: (msg: string, ...args: unknown[]) => void
  readonly error: (msg: string, ...args: unknown[]) => void
}

const defaultLogger: ReminderWorkerLogger = {
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

export type ReminderSendResult =
  { readonly ok: true } | { readonly ok: false; readonly reason: string }

export type ReminderSender = (args: {
  readonly to: string
  readonly text: string
  readonly env: NodeJS.ProcessEnv
  readonly channels?: ReadonlyMap<ChannelKind, ChannelPort>
}) => Promise<ReminderSendResult>

/** `【提醒】交周报`; late sends carry the original scheduled time. */
export function formatReminderMessage(reminder: ReminderRecord, nowMs: number): string {
  const prefix = reminder.repeat === "daily" ? "【提醒】每天提醒" : "【提醒】"
  const late = nowMs - reminder.fireAtMs > LATE_THRESHOLD_MS
  const head = `${prefix}${reminder.content}`
  return late ? `${head}\n（原定 ${formatReminderTime(reminder.fireAtMs)}，补发）` : head
}

function auditMissed(args: {
  readonly runtimeStore?: RuntimeStore | null
  readonly reminder: ReminderRecord
  readonly nowMs: number
  readonly reason: string
}): void {
  const store = args.runtimeStore
  if (!store) return
  void store
    .appendAuditEvent({
      auditId: crypto.randomUUID(),
      runId: null,
      conversationId: args.reminder.conversationId,
      correlationId: args.reminder.conversationId,
      action: "reminder.missed",
      actor: "owner-direct",
      subject: args.reminder.subject,
      detail: {
        reminderId: args.reminder.id,
        fireAt: new Date(args.reminder.fireAtMs).toISOString(),
        lateMs: args.nowMs - args.reminder.fireAtMs,
        reason: args.reason,
      },
      createdAt: new Date(args.nowMs),
    })
    .catch((err: unknown) => {
      // eslint-disable-next-line no-console -- operator log
      console.error("[reminder-worker] reminder.missed audit failed:", err)
    })
}

function auditFired(args: {
  readonly runtimeStore?: RuntimeStore | null
  readonly reminder: ReminderRecord
  readonly nowMs: number
}): void {
  const store = args.runtimeStore
  if (!store) return
  void store
    .appendAuditEvent({
      auditId: crypto.randomUUID(),
      runId: null,
      conversationId: args.reminder.conversationId,
      correlationId: args.reminder.conversationId,
      action: "reminder.fired",
      actor: "owner-direct",
      subject: args.reminder.subject,
      detail: {
        reminderId: args.reminder.id,
        repeat: args.reminder.repeat,
        fireAt: new Date(args.reminder.fireAtMs).toISOString(),
        lateMs: Math.max(0, args.nowMs - args.reminder.fireAtMs),
      },
      createdAt: new Date(args.nowMs),
    })
    .catch((err: unknown) => {
      // eslint-disable-next-line no-console -- operator log
      console.error("[reminder-worker] reminder.fired audit failed:", err)
    })
}

export interface ReminderTickStats {
  readonly fired: number
  readonly failed: number
}

/** Deliver every due reminder once. Exported for tests. */
export async function runReminderTick(args: {
  readonly wiring: Wiring
  readonly env?: NodeJS.ProcessEnv
  readonly nowMs?: () => number
  readonly send?: ReminderSender
  readonly logger?: ReminderWorkerLogger
}): Promise<ReminderTickStats> {
  const store = args.wiring.reminderStore
  if (!store) return { fired: 0, failed: 0 }
  const env = args.env ?? process.env
  const logger = args.logger ?? defaultLogger
  const send = args.send ?? sendWechatText
  const nowMs = args.nowMs?.() ?? Date.now()

  const due = await store.listDue({
    nowMs,
    retryCooldownMs: RETRY_COOLDOWN_MS,
    limit: 20,
  })

  let fired = 0
  let failed = 0
  for (const reminder of due) {
    const text = formatReminderMessage(reminder, nowMs)
    const result = await send({
      to: reminder.wechatUserId,
      text,
      env,
      ...(args.wiring.channels.size === 0 ? {} : { channels: args.wiring.channels }),
    })
    if (!result.ok) {
      failed += 1
      await store.markAttemptFailed({
        id: reminder.id,
        error: result.reason,
        attemptedAtMs: nowMs,
      })
      logger.warn(`[reminder] send failed id=${reminder.id}: ${result.reason}`)
      continue
    }
    const next = nextReminderFireAtMs(reminder.fireAtMs, reminder.repeat)
    await store.markFired({
      id: reminder.id,
      ...(next === undefined ? {} : { nextFireAtMs: next }),
      firedAtMs: nowMs,
    })
    fired += 1
    if (nowMs - reminder.fireAtMs > LATE_THRESHOLD_MS) {
      auditMissed({
        runtimeStore: args.wiring.runtimeStore,
        reminder,
        nowMs,
        reason: "late_delivery",
      })
    }
    auditFired({ runtimeStore: args.wiring.runtimeStore, reminder, nowMs })
    logger.info(`[reminder] fired id=${reminder.id} repeat=${reminder.repeat}`)
  }
  return { fired, failed }
}

export interface ReminderWorkerHandle {
  readonly stop: () => void
}

/** Start the opt-in reminder poller. No-op when disabled or no store. */
export function startReminderWorkerIfEnabled(args: {
  readonly wiring: Wiring
  readonly env?: NodeJS.ProcessEnv
  readonly config?: ReminderConfig
  readonly logger?: ReminderWorkerLogger
}): ReminderWorkerHandle | null {
  const env = args.env ?? process.env
  const config = args.config ?? parseReminderConfig(env)
  const logger = args.logger ?? defaultLogger
  if (!config.enabled) return null
  if (!args.wiring.reminderStore) {
    logger.warn("[reminder] enabled but reminder store is unavailable; worker not started")
    return null
  }

  let stopped = false
  let timer: ReturnType<typeof setTimeout> | null = null

  const tick = async (): Promise<void> => {
    if (stopped) return
    try {
      await runReminderTick({ wiring: args.wiring, env, logger })
    } catch (err) {
      logger.error("[reminder] tick failed:", err instanceof Error ? err.message : String(err))
    }
    if (stopped) return
    timer = setTimeout(() => {
      void tick()
    }, config.tickMs)
  }

  logger.info(`[reminder] worker started tickMs=${config.tickMs}`)
  void tick()

  return {
    stop: () => {
      stopped = true
      if (timer) clearTimeout(timer)
      timer = null
    },
  }
}
