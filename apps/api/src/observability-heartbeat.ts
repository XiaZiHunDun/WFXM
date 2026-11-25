/**
 * Phase 6 P1: periodic observability heartbeat.
 *
 * The loop's "信息收集 → 分析" stage previously required the owner to ask
 * `/诊断` manually. That is not a closed loop: a failure can sit unnoticed
 * until someone happens to look. This worker reuses the exact diagnostics
 * aggregate and pushes a WeChat alert when a signal crosses a threshold,
 * with per-signal silence so a persistent condition is not spam.
 *
 * Deliberately simple:
 *   - signals are derived from `collectDiagnostics` (one source of truth),
 *   - silence state is in-memory (restart re-alerts once),
 *   - no recipient configured → only logs / audits, never invents a target.
 */
import { collectDiagnostics } from "./diagnostics.js"
import { envTruthy, parsePositiveInt } from "./env-util.js"
import { formatReminderTime } from "./reminder-time.js"
import { sendWechatText } from "./wechat-run-notify.js"
import type { Wiring } from "./wiring.js"

export interface AlertSignal {
  /** Stable dedupe key — must not embed counters that change every tick. */
  readonly key: string
  readonly text: string
}

export interface AlertConfig {
  readonly enabled: boolean
  readonly intervalMs: number
  readonly silenceMs: number
  readonly failureThreshold: number
  readonly to: string | null
}

export type HeartbeatLogger = {
  readonly info: (msg: string, ...args: unknown[]) => void
  readonly error: (msg: string, ...args: unknown[]) => void
}

const defaultLogger: HeartbeatLogger = {
  info: (msg, ...args) => {
    // eslint-disable-next-line no-console -- operator log
    console.info(msg, ...args)
  },
  error: (msg, ...args) => {
    // eslint-disable-next-line no-console -- operator log
    console.error(msg, ...args)
  },
}

function firstCsvId(raw: string | undefined): string | null {
  const first = (raw ?? "")
    .split(",")
    .map((part) => part.trim())
    .find((part) => part.length > 0)
  return first ?? null
}

export function parseAlertConfig(env: NodeJS.ProcessEnv = process.env): AlertConfig {
  return {
    enabled: envTruthy(env["BUTLER_V5_ALERT_ENABLED"] ?? "1"),
    intervalMs: parsePositiveInt(env["BUTLER_V5_ALERT_INTERVAL_MS"], 5 * 60_000),
    silenceMs: parsePositiveInt(env["BUTLER_V5_ALERT_SILENCE_MS"], 6 * 60 * 60_000),
    failureThreshold: parsePositiveInt(env["BUTLER_V5_ALERT_FAILURE_THRESHOLD"], 20),
    to: (env["BUTLER_V5_ALERT_TO"] ?? "").trim() || firstCsvId(env["BUTLER_OWNER_WECHAT_ID"]),
  }
}

export function evaluateAlertSignals(
  report: Awaited<ReturnType<typeof collectDiagnostics>>,
  failureThreshold: number,
): readonly AlertSignal[] {
  const signals: AlertSignal[] = []
  if (report.checks.db.status !== "up") {
    signals.push({ key: "db_down", text: "数据库异常（诊断聚合失败）" })
  }
  if (report.checks.outbox.failed > 0) {
    signals.push({
      key: "outbox_failed",
      text: `待发消息失败 ${report.checks.outbox.failed} 条`,
    })
  }
  if (report.checks.traces.dropped > 0) {
    signals.push({
      key: "trace_dropped",
      text: `轨迹写入丢弃 ${report.checks.traces.dropped} 条（事件观察存在缺口）`,
    })
  }
  const failures = report.checks.failures
  if (failures.total > failureThreshold) {
    const top = failures.clusters[0]
    signals.push({
      key: "failure_rate",
      text: `近 7 天失败 ${failures.total} 次（阈值 ${failureThreshold}）${
        top ? `，最多：${top.key}（${top.count}）` : ""
      }`,
    })
  }
  const baseline = report.eval_baseline
  if (baseline.stale && baseline.count > 0) {
    signals.push({
      key: "eval_baseline_stale",
      text: `回归基线已 ${baseline.age_days} 天未更新（阈值 ${baseline.max_age_days} 天）`,
    })
  }
  return signals
}

export function renderAlert(signals: readonly AlertSignal[], nowMs: number = Date.now()): string {
  return [
    `【系统告警】${formatReminderTime(nowMs)}`,
    ...signals.map((signal) => `· ${signal.text}`),
    "回复「/诊断」查看详情。",
  ].join("\n")
}

async function recordAlertAudit(args: {
  readonly wiring: Wiring
  readonly keys: readonly string[]
  readonly nowMs: number
}): Promise<void> {
  try {
    await args.wiring.runtimeStore.appendAuditEvent({
      auditId: crypto.randomUUID(),
      runId: null,
      conversationId: null,
      correlationId: null,
      action: "alert.sent",
      actor: "system",
      subject: "owner",
      detail: { keys: [...args.keys] },
      createdAt: new Date(args.nowMs),
    })
  } catch (err) {
    // eslint-disable-next-line no-console -- alerting must not break the tick
    console.error("[observability-heartbeat] audit failed:", err)
  }
}

export interface HeartbeatTickResult {
  readonly signals: readonly AlertSignal[]
  readonly fresh: readonly AlertSignal[]
  readonly sent: boolean
  readonly reason: "disabled" | "healthy" | "silenced" | "no_recipient" | "send_failed" | "sent"
}

/** Evaluate one heartbeat tick. Exported for tests. */
export async function runHeartbeatTick(args: {
  readonly wiring: Wiring
  readonly env?: NodeJS.ProcessEnv
  readonly config?: AlertConfig
  readonly nowMs?: number
  readonly lastSent?: Map<string, number>
  readonly send?: typeof sendWechatText
  readonly logger?: HeartbeatLogger
}): Promise<HeartbeatTickResult> {
  const env = args.env ?? process.env
  const config = args.config ?? parseAlertConfig(env)
  if (!config.enabled) {
    return { signals: [], fresh: [], sent: false, reason: "disabled" }
  }
  const nowMs = args.nowMs ?? Date.now()
  const logger = args.logger ?? defaultLogger
  const lastSent = args.lastSent ?? new Map<string, number>()

  const report = await collectDiagnostics(args.wiring, env, nowMs)
  const signals = evaluateAlertSignals(report, config.failureThreshold)
  if (signals.length === 0) {
    logger.info("[observability-heartbeat] healthy")
    return { signals, fresh: [], sent: false, reason: "healthy" }
  }

  const fresh = signals.filter((signal) => {
    const previous = lastSent.get(signal.key)
    return previous === undefined || nowMs - previous >= config.silenceMs
  })
  if (fresh.length === 0) {
    logger.info(`[observability-heartbeat] silenced signals=${signals.length}`)
    return { signals, fresh, sent: false, reason: "silenced" }
  }

  if (!config.to) {
    logger.error(
      `[observability-heartbeat] alert but no recipient (set BUTLER_V5_ALERT_TO or BUTLER_OWNER_WECHAT_ID) keys=${fresh
        .map((signal) => signal.key)
        .join(",")}`,
    )
    return { signals, fresh, sent: false, reason: "no_recipient" }
  }

  const result = await (args.send ?? sendWechatText)({
    to: config.to,
    text: renderAlert(fresh, nowMs),
    env,
    ...(args.wiring.channels.size === 0 ? {} : { channels: args.wiring.channels }),
  })
  if (!result.ok) {
    logger.error(`[observability-heartbeat] send failed: ${result.reason}`)
    return { signals, fresh, sent: false, reason: "send_failed" }
  }

  for (const signal of fresh) lastSent.set(signal.key, nowMs)
  await recordAlertAudit({ wiring: args.wiring, keys: fresh.map((signal) => signal.key), nowMs })
  logger.info(`[observability-heartbeat] alert sent signals=${fresh.length}`)
  return { signals, fresh, sent: true, reason: "sent" }
}

export interface HeartbeatHandle {
  readonly stop: () => void
}

/** Start the periodic heartbeat. No-op under vitest and when disabled. */
export function startObservabilityHeartbeatIfEnabled(args: {
  readonly wiring: Wiring
  readonly env?: NodeJS.ProcessEnv
  readonly config?: AlertConfig
  readonly logger?: HeartbeatLogger
  readonly send?: typeof sendWechatText
}): HeartbeatHandle | null {
  const env = args.env ?? process.env
  if ((env["VITEST"] ?? "").trim() !== "") return null
  const config = args.config ?? parseAlertConfig(env)
  if (!config.enabled) return null

  const logger = args.logger ?? defaultLogger
  const lastSent = new Map<string, number>()
  let stopped = false
  let timer: ReturnType<typeof setTimeout> | null = null

  const tick = async (): Promise<void> => {
    if (stopped) return
    try {
      await runHeartbeatTick({
        wiring: args.wiring,
        env,
        config,
        lastSent,
        logger,
        ...(args.send === undefined ? {} : { send: args.send }),
      })
    } catch (err) {
      logger.error(
        "[observability-heartbeat] tick failed:",
        err instanceof Error ? err.message : String(err),
      )
    }
    if (stopped) return
    timer = setTimeout(() => {
      void tick()
    }, config.intervalMs)
    if (typeof timer.unref === "function") timer.unref()
  }

  logger.info(
    `[observability-heartbeat] started intervalMs=${config.intervalMs} silenceMs=${config.silenceMs} to=${config.to ?? "(none)"}`,
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
