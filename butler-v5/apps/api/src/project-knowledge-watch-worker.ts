/**
 * Opt-in Project Knowledge sources watch worker (K1.1).
 */
import {
  isProjectKnowledgeWatchEnabled,
  loadProjectKnowledgeSourcesFromEnv,
  parseProjectKnowledgeWatchConfig,
  type ProjectKnowledgeWatchConfig,
} from "./project-knowledge-sources-config.js"
import { syncProjectKnowledgeFromManifest } from "./project-knowledge-sync.js"
import type { Wiring } from "./wiring.js"

export type ProjectKnowledgeWatchLogger = {
  readonly info: (msg: string, ...args: unknown[]) => void
  readonly warn: (msg: string, ...args: unknown[]) => void
  readonly error: (msg: string, ...args: unknown[]) => void
}

export type ProjectKnowledgeWatchHandle = {
  readonly stop: () => void
}

const defaultLogger: ProjectKnowledgeWatchLogger = {
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

export async function runProjectKnowledgeWatchTick(args: {
  readonly wiring: Wiring
  readonly env?: NodeJS.ProcessEnv
  readonly cwd?: string
  readonly logger?: ProjectKnowledgeWatchLogger
}): Promise<{ readonly ok: boolean; readonly reason?: string; readonly stats?: Awaited<ReturnType<typeof syncProjectKnowledgeFromManifest>> }> {
  const env = args.env ?? process.env
  const cwd = args.cwd ?? process.cwd()
  const logger = args.logger ?? defaultLogger
  const loaded = loadProjectKnowledgeSourcesFromEnv(env, cwd)
  if (loaded.kind === "none") {
    return { ok: false, reason: "no sources manifest configured" }
  }
  if (loaded.kind === "error") {
    return { ok: false, reason: loaded.reason }
  }
  const stats = await syncProjectKnowledgeFromManifest({
    wiring: args.wiring,
    manifest: loaded.manifest,
    env,
  })
  if (stats.errors.length > 0) {
    logger.warn(`[project-knowledge-watch] sync errors=${stats.errors.length}`, stats.errors.slice(0, 3))
  }
  logger.info(
    `[project-knowledge-watch] scanned=${stats.scanned} created=${stats.created} updated=${stats.updated} skipped=${stats.skipped}`,
  )
  return { ok: true, stats }
}

export function startProjectKnowledgeWatchWorkerIfEnabled(args: {
  readonly wiring: Wiring
  readonly env?: NodeJS.ProcessEnv
  readonly config?: ProjectKnowledgeWatchConfig
  readonly cwd?: string
  readonly logger?: ProjectKnowledgeWatchLogger
}): ProjectKnowledgeWatchHandle | null {
  const env = args.env ?? process.env
  const config = args.config ?? parseProjectKnowledgeWatchConfig(env)
  const logger = args.logger ?? defaultLogger
  if (!config.enabled) return null
  if (!isProjectKnowledgeWatchEnabled(env)) return null

  let stopped = false
  let timer: ReturnType<typeof setTimeout> | null = null
  let inFlight = false

  const tick = async (): Promise<void> => {
    if (stopped || inFlight) return
    inFlight = true
    try {
      await runProjectKnowledgeWatchTick({
        wiring: args.wiring,
        env,
        cwd: args.cwd,
        logger,
      })
    } catch (err) {
      logger.error(
        "[project-knowledge-watch] tick failed:",
        err instanceof Error ? err.message : String(err),
      )
    } finally {
      inFlight = false
      if (!stopped) {
        timer = setTimeout(() => {
          void tick()
        }, config.tickMs)
      }
    }
  }

  logger.info(`[project-knowledge-watch] worker started tickMs=${config.tickMs}`)
  void tick()

  return {
    stop: () => {
      stopped = true
      if (timer) clearTimeout(timer)
      timer = null
    },
  }
}
