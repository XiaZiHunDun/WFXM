/**
 * Schedule / Heartbeat worker — produces RunTriggers on an interval.
 * Opt-in via BUTLER_V5_SCHEDULE_ENABLED=1. Does not own Policy or a second engine.
 */
import { evaluateScheduleTick, type ScheduleJobSpec } from "@butler/domain/runtime.js"
import { isActiveMainRunStatus } from "@butler/domain/runtime.js"
import { parseScheduleWorkerConfig, type ScheduleWorkerConfig } from "./schedule-config.js"
import { runScheduleJob } from "./schedule-run.js"
import type { Wiring } from "./wiring.js"

export type ScheduleWorkerLogger = {
  readonly info: (msg: string, ...args: unknown[]) => void
  readonly warn: (msg: string, ...args: unknown[]) => void
  readonly error: (msg: string, ...args: unknown[]) => void
}

export type ScheduleWorkerHandle = {
  readonly stop: () => void
}

const defaultLogger: ScheduleWorkerLogger = {
  info: (msg, ...args) => {
    // eslint-disable-next-line no-console -- operator log
    console.error(msg, ...args)
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

export interface ScheduleTickDeps {
  readonly wiring: Wiring
  readonly jobs: readonly ScheduleJobSpec[]
  readonly nowMs: () => number
  readonly lastAttemptByJob: Map<string, number>
  readonly scheduleInFlight: { value: boolean }
  readonly isMainQueueBusy: () => boolean | Promise<boolean>
  readonly env?: NodeJS.ProcessEnv
  readonly logger?: ScheduleWorkerLogger
}

export type ScheduleTickStats = {
  readonly fired: number
  readonly deferred: number
  readonly skipped: number
}

/**
 * Evaluate all jobs once. Exported for tests.
 */
export async function runScheduleTick(deps: ScheduleTickDeps): Promise<ScheduleTickStats> {
  const logger = deps.logger ?? defaultLogger
  let fired = 0
  let deferred = 0
  let skipped = 0

  for (const job of deps.jobs) {
    const conversationId =
      job.conversationId?.trim() || `schedule-${job.id}`
    let conversationBusy = false
    try {
      const active = await deps.wiring.runtimeStore.findActiveMainRun(conversationId)
      conversationBusy = Boolean(active && isActiveMainRunStatus(active.status))
    } catch (err) {
      logger.warn(
        `[schedule] findActiveMainRun failed for ${conversationId}:`,
        err instanceof Error ? err.message : String(err),
      )
      conversationBusy = true
    }

    const mainQueueBusy = await deps.isMainQueueBusy()
    const decision = evaluateScheduleTick({
      job,
      nowMs: deps.nowMs(),
      lastAttemptMs: deps.lastAttemptByJob.get(job.id) ?? null,
      conversationBusy,
      mainQueueBusy,
      scheduleInFlight: deps.scheduleInFlight.value,
    })

    if (decision._tag === "skip") {
      skipped += 1
      continue
    }
    if (decision._tag === "defer") {
      deferred += 1
      logger.info(`[schedule] defer job=${job.id} reason=${decision.reason}`)
      continue
    }

    deps.scheduleInFlight.value = true
    try {
      const result = await runScheduleJob({
        wiring: deps.wiring,
        job: decision.job,
        conversationId: decision.conversationId,
        idempotencyKey: decision.idempotencyKey,
        deadline: decision.deadline,
        env: deps.env,
      })
      fired += 1
      deps.lastAttemptByJob.set(job.id, deps.nowMs())
      if (result.quiet) {
        logger.info(`[schedule] quiet success job=${job.id}`)
      } else {
        logger.info(
          `[schedule] fired job=${job.id} decision=${result.loop.finalDecision} reply=${result.loop.reply.slice(0, 120)}`,
        )
      }
    } catch (err) {
      deferred += 1
      deps.lastAttemptByJob.set(job.id, deps.nowMs())
      logger.error(
        `[schedule] fire failed job=${job.id}:`,
        err instanceof Error ? err.message : String(err),
      )
    } finally {
      deps.scheduleInFlight.value = false
    }
  }

  return { fired, deferred, skipped }
}

/**
 * Start the opt-in schedule poller. No-op when disabled or no jobs.
 */
export function startScheduleWorkerIfEnabled(args: {
  readonly wiring: Wiring
  readonly env?: NodeJS.ProcessEnv
  readonly config?: ScheduleWorkerConfig
  readonly logger?: ScheduleWorkerLogger
  /** Injectable busy signal (e.g. wechat inbound in flight). */
  readonly isMainQueueBusy?: () => boolean | Promise<boolean>
}): ScheduleWorkerHandle | null {
  const env = args.env ?? process.env
  const config = args.config ?? parseScheduleWorkerConfig(env)
  const logger = args.logger ?? defaultLogger
  if (!config.enabled) return null
  if (config.jobs.length === 0) {
    logger.warn("[schedule] enabled but no jobs configured; worker not started")
    return null
  }

  const lastAttemptByJob = new Map<string, number>()
  const scheduleInFlight = { value: false }
  let stopped = false
  let timer: ReturnType<typeof setTimeout> | null = null

  const isMainQueueBusy = async (): Promise<boolean> => {
    if (!config.deferWhenMainBusy) return false
    if (args.isMainQueueBusy) return Boolean(await args.isMainQueueBusy())
    return false
  }

  const tick = async (): Promise<void> => {
    if (stopped) return
    try {
      await runScheduleTick({
        wiring: args.wiring,
        jobs: config.jobs,
        nowMs: () => Date.now(),
        lastAttemptByJob,
        scheduleInFlight,
        isMainQueueBusy,
        env,
        logger,
      })
    } catch (err) {
      logger.error(
        "[schedule] tick failed:",
        err instanceof Error ? err.message : String(err),
      )
    } finally {
      if (!stopped) {
        timer = setTimeout(() => {
          void tick()
        }, config.tickMs)
      }
    }
  }

  logger.info(
    `[schedule] worker started jobs=${config.jobs.length} tickMs=${config.tickMs}`,
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
