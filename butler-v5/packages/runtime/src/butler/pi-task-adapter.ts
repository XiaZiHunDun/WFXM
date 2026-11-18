/**
 * ButlerTaskPort -> PiTaskRunner adapter.
 *
 * The butler runtime only sees `ButlerTaskPort`. This adapter owns the
 * pi-specific details: task ids, project cwd resolution, turn/session status
 * and approval forwarding.
 */
import { randomUUID } from "node:crypto"
import type { ButlerTaskPort, ButlerTaskRef } from "@butler/ports/core/butler-task.js"
import type { PiTaskSessionRecord } from "@butler/ports/core/pi-task-session.js"
import type { PiTaskRunner } from "../execution/pi-task-runner.js"
import { buildRepoMap } from "../execution/repo-map.js"
import { DEFAULT_PI_TASK_SYSTEM_PROMPT } from "../execution/pi-task-prompt.js"

export interface PiTaskPortAdapterOptions {
  /** Project id -> workspace directory. */
  readonly resolveCwd: (projectId: string) => string | Promise<string>
  readonly newTaskId?: (projectId: string) => string
  readonly timeoutMs?: number
  /**
   * Injects a compact repository outline (paths + a few symbols) into the task
   * system prompt. Default on; set false to save tokens on huge repos.
   */
  readonly repoMap?: boolean
  readonly repoMapMaxChars?: number
  /** Base system prompt used when a repo map is injected. */
  readonly systemPrompt?: string
  /**
   * `false` (default) waits for the first turn, so the butler can report the
   * outcome. `true` returns as soon as the turn is running; the owner polls
   * `/status` for the result.
   */
  readonly detached?: boolean
  readonly logger?: { warn(message: string, extra?: unknown): void }
}

export interface PiTaskPortAdapter extends ButlerTaskPort {
  /** Resolves once every detached/inline turn started by this adapter settles. */
  idle(): Promise<void>
}

function defaultTaskId(): string {
  return `task-${Date.now().toString(36)}-${randomUUID().slice(0, 8)}`
}

function toRef(record: PiTaskSessionRecord): ButlerTaskRef {
  const pending = record.pendingStep
  return {
    taskId: record.taskId,
    projectId: record.projectId,
    status: record.status,
    ...(record.snapshot.summary === undefined ? {} : { summary: record.snapshot.summary }),
    ...(pending === null
      ? {}
      : {
          pending: {
            toolName: pending.toolName,
            reason: pending.reason,
            requestedAt: pending.requestedAt,
          },
        }),
  }
}

export function createPiTaskPortAdapter(
  runner: PiTaskRunner,
  options: PiTaskPortAdapterOptions,
): PiTaskPortAdapter {
  const newTaskId = options.newTaskId ?? defaultTaskId
  const inFlight = new Set<string>()
  const pending = new Set<Promise<unknown>>()
  const logger = options.logger ?? {
    warn: (message, extra) => {
      // eslint-disable-next-line no-console -- operator-facing warning
      console.warn(message, extra ?? "")
    },
  }

  const track = (taskId: string, run: Promise<unknown>): Promise<unknown> => {
    inFlight.add(taskId)
    const settled = run
      .catch((error) => {
        logger.warn(`[butler-task] ${taskId} turn failed`, error)
      })
      .finally(() => {
        inFlight.delete(taskId)
        pending.delete(settled)
      })
    pending.add(settled)
    return settled
  }

  const turnOptions = options.timeoutMs === undefined ? {} : { timeoutMs: options.timeoutMs }
  const repoMaps = new Map<string, { text: string; expiresAt: number }>()
  const REPO_MAP_TTL_MS = 300_000

  const repoMapFor = async (cwd: string): Promise<string> => {
    if (options.repoMap === false) return ""
    const cached = repoMaps.get(cwd)
    if (cached && cached.expiresAt > Date.now()) return cached.text
    try {
      const text = await buildRepoMap(cwd, {
        ...(options.repoMapMaxChars === undefined ? {} : { maxChars: options.repoMapMaxChars }),
      })
      repoMaps.set(cwd, { text, expiresAt: Date.now() + REPO_MAP_TTL_MS })
      return text
    } catch (error) {
      logger.warn(`[butler-task] repo map failed for ${cwd}`, error)
      return ""
    }
  }

  const statusOf = async (taskId: string): Promise<ButlerTaskRef | null> => {
    const record = await runner.load(taskId)
    if (!record) return null
    return inFlight.has(taskId) ? { ...toRef(record), status: "running" } : toRef(record)
  }

  return {
    async start(input): Promise<ButlerTaskRef> {
      const taskId = newTaskId(input.projectId)
      const cwd = await options.resolveCwd(input.projectId)
      const repoMap = await repoMapFor(cwd)
      const record = await runner.open({
        taskId,
        projectId: input.projectId,
        cwd,
        summary: input.goal,
        ...(repoMap.length === 0
          ? {}
          : {
              systemPrompt: `${options.systemPrompt ?? DEFAULT_PI_TASK_SYSTEM_PROMPT}\n\n${repoMap}`,
            }),
      })

      const run = runner.start(taskId, input.goal, turnOptions)
      if (options.detached === true) {
        void track(taskId, run)
        return { ...toRef(record), status: "running" }
      }

      await track(taskId, run)
      return (await statusOf(taskId)) ?? { ...toRef(record), status: "failed" }
    },

    status: statusOf,

    async list(projectId): Promise<readonly ButlerTaskRef[]> {
      const refs = runner.list().map((record) => {
        const ref = toRef(record)
        return inFlight.has(ref.taskId) ? { ...ref, status: "running" as const } : ref
      })
      return projectId === undefined ? refs : refs.filter((ref) => ref.projectId === projectId)
    },

    async approve(taskId, approved): Promise<ButlerTaskRef | null> {
      const record = await runner.load(taskId)
      if (!record) return null
      if (record.status !== "paused" || record.pendingStep === null) return null
      const run = runner.resume(taskId, { approved })
      await track(taskId, run)
      return (await statusOf(taskId)) ?? toRef(record)
    },

    async idle(): Promise<void> {
      await Promise.allSettled([...pending])
    },
  }
}
