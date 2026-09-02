/**
 * G1: opt-in in-process candidate expires sweeper.
 * Same pattern as schedule-worker: env-gated, setInterval, logger, no second Loop.
 */
import { expireOldCandidates, DEFAULT_EXPIRE_TTL_MS, DEFAULT_EXPIRE_BATCH_LIMIT } from "@butler/domain/knowledge/candidate-expires.js"
import { envTruthy, parsePositiveInt } from "./env-util.js"
import type { Wiring } from "./wiring.js"

export type CandidateExpiresLogger = {
  readonly info: (msg: string, ...args: unknown[]) => void
  readonly error: (msg: string, ...args: unknown[]) => void
}

export type CandidateExpiresSweeperHandle = {
  readonly stop: () => void
}

export interface CandidateExpiresSweeperConfig {
  readonly enabled: boolean
  readonly tickMs: number
  readonly ttlMs: number
  readonly batchLimit?: number
}

export function parseCandidateExpiresSweeperConfig(
  env: NodeJS.ProcessEnv,
): CandidateExpiresSweeperConfig {
  return {
    enabled: envTruthy(env["BUTLER_V5_CANDIDATE_EXPIRES_ENABLED"]),
    tickMs: parsePositiveInt(
      env["BUTLER_V5_CANDIDATE_EXPIRES_INTERVAL_MS"],
      3_600_000,
    ),
    ttlMs: parsePositiveInt(
      env["BUTLER_V5_CANDIDATE_EXPIRES_TTL_MS"],
      DEFAULT_EXPIRE_TTL_MS,
    ),
    batchLimit: parsePositiveInt(
      env["BUTLER_V5_CANDIDATE_EXPIRES_BATCH_LIMIT"],
      DEFAULT_EXPIRE_BATCH_LIMIT,
    ),
  }
}

const defaultLogger: CandidateExpiresLogger = {
  info: (msg, ...args) => {
    // eslint-disable-next-line no-console -- operator log
    console.error(msg, ...args)
  },
  error: (msg, ...args) => {
    // eslint-disable-next-line no-console -- operator log
    console.error(msg, ...args)
  },
}

export interface SweeperTickDeps {
  readonly wiring: Wiring
  readonly ttlMs: number
  readonly batchLimit?: number
  readonly now?: () => Date
  readonly logger?: CandidateExpiresLogger
}

export async function runCandidateExpiresTick(
  deps: SweeperTickDeps,
): Promise<{ scanned: number; expired: number }> {
  const logger = deps.logger ?? defaultLogger
  const store = deps.wiring.durableMemoryStore
  if (!store) {
    logger.error("[candidate-expires] tick skipped: durableMemoryStore not wired")
    return { scanned: 0, expired: 0 }
  }
  try {
    const result = await expireOldCandidates({
      store,
      now: deps.now?.() ?? new Date(),
      ttlMs: deps.ttlMs,
      ...(deps.batchLimit === undefined ? {} : { batchLimit: deps.batchLimit }),
    })
    logger.info(
      `[candidate-expires] scanned=${result.scanned} expired=${result.expired} olderThanMs=${result.olderThanMs}`,
    )
    return { scanned: result.scanned, expired: result.expired }
  } catch (err) {
    logger.error(
      "[candidate-expires] tick failed:",
      err instanceof Error ? err.message : String(err),
    )
    return { scanned: 0, expired: 0 }
  }
}

export function startCandidateExpiresSweeperIfEnabled(args: {
  readonly wiring: Wiring
  readonly env?: NodeJS.ProcessEnv
  readonly config?: CandidateExpiresSweeperConfig
  readonly logger?: CandidateExpiresLogger
}): CandidateExpiresSweeperHandle | null {
  const env = args.env ?? process.env
  const config = args.config ?? parseCandidateExpiresSweeperConfig(env)
  if (!config.enabled) return null

  const logger = args.logger ?? defaultLogger
  let stopped = false
  let timer: ReturnType<typeof setTimeout> | null = null

  const tick = async (): Promise<void> => {
    if (stopped) return
    await runCandidateExpiresTick({
      wiring: args.wiring,
      ttlMs: config.ttlMs,
      ...(config.batchLimit === undefined ? {} : { batchLimit: config.batchLimit }),
      logger,
    })
    if (!stopped) {
      timer = setTimeout(() => {
        void tick()
      }, config.tickMs)
    }
  }

  logger.info(
    `[candidate-expires] sweeper started tickMs=${config.tickMs} ttlMs=${config.ttlMs}`,
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