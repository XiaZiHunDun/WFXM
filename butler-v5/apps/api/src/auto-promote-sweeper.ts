/**
 * G4: opt-in in-process candidate auto-promote sweeper.
 * Same pattern as schedule-worker: env-gated, setInterval, logger, no second Loop.
 * Sweeps candidates older than windowMs; promotes to confirmed (status='confirmed', promoted_by='sweeper', promoted_at=now).
 */

import { autoPromoteOldCandidates } from "@butler/domain/knowledge/auto-promote.js"
import type { AutoPromoteConfig } from "./auto-promote-config.js"
import type { Wiring } from "./wiring.js"

export type AutoPromoteLogger = {
  readonly info: (msg: string, ...args: unknown[]) => void
  readonly error: (msg: string, ...args: unknown[]) => void
}

export type AutoPromoteSweeperHandle = {
  readonly stop: () => void
}

export interface AutoPromoteTickDeps {
  readonly wiring: Wiring
  readonly config: AutoPromoteConfig
  readonly now?: () => Date
  readonly logger?: AutoPromoteLogger
}

export async function runAutoPromoteTick(
  deps: AutoPromoteTickDeps,
): Promise<{ scanned: number; promoted: number }> {
  const logger = deps.logger ?? defaultLogger
  const now = deps.now?.() ?? new Date()
  const store = deps.wiring.durableMemoryStore
  if (!store) {
    logger.error("[memory-auto-promote] tick skipped: durableMemoryStore not wired")
    return { scanned: 0, promoted: 0 }
  }
  try {
    const candidates = await store.findAutoPromoteCandidates({
      now,
      windowMs: deps.config.windowMs,
      limit: deps.config.sweepLimit,
    })
    const { toPromote } = autoPromoteOldCandidates({
      candidates,
      now,
      windowMs: deps.config.windowMs,
    })
    if (toPromote.length === 0) {
      logger.info(
        `[memory-auto-promote] scanned=${candidates.length} promoted=0 windowMs=${deps.config.windowMs}`,
      )
      return { scanned: candidates.length, promoted: 0 }
    }
    const count = await store.markAutoPromoted({
      ids: toPromote.map((c) => c.id),
      now,
    })
    logger.info(
      `[memory-auto-promote] scanned=${candidates.length} promoted=${count} windowMs=${deps.config.windowMs}`,
    )
    return { scanned: candidates.length, promoted: count }
  } catch (err) {
    logger.error(
      "[memory-auto-promote] tick failed:",
      err instanceof Error ? err.message : String(err),
    )
    return { scanned: 0, promoted: 0 }
  }
}

const defaultLogger: AutoPromoteLogger = {
  info: (msg, ...args) => {
    // eslint-disable-next-line no-console -- operator log
    console.error(msg, ...args)
  },
  error: (msg, ...args) => {
    // eslint-disable-next-line no-console -- operator log
    console.error(msg, ...args)
  },
}

export function startAutoPromoteSweeperIfEnabled(args: {
  readonly wiring: Wiring
  readonly config: AutoPromoteConfig
  readonly logger?: AutoPromoteLogger
}): AutoPromoteSweeperHandle | null {
  if (!args.config.enabled) return null

  const logger = args.logger ?? defaultLogger
  let stopped = false
  let timer: ReturnType<typeof setTimeout> | null = null

  const tick = async (): Promise<void> => {
    if (stopped) return
    await runAutoPromoteTick({
      wiring: args.wiring,
      config: args.config,
      logger,
    })
    if (!stopped) {
      timer = setTimeout(() => {
        void tick()
      }, args.config.sweepIntervalMs)
    }
  }

  logger.info(
    `[memory-auto-promote] sweeper started intervalMs=${args.config.sweepIntervalMs} windowMs=${args.config.windowMs}`,
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
