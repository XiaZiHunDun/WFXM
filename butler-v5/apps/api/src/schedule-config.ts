/**
 * Opt-in Schedule / Heartbeat config.
 *
 * BUTLER_V5_SCHEDULE_ENABLED=1
 * BUTLER_V5_SCHEDULE_TICK_MS=60000
 * BUTLER_V5_SCHEDULE_JOBS_PATH=config/schedule-jobs.json
 *   or inline JSON: BUTLER_V5_SCHEDULE_JOBS=[...]
 */
import { readFileSync } from "node:fs"
import { envTruthy } from "./env-util.js"
import { resolve } from "node:path"
import type { ScheduleJobSpec } from "@butler/domain/runtime.js"


function asPositiveInt(raw: unknown, fallback: number): number {
  const n = typeof raw === "number" ? raw : Number(raw)
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : fallback
}

function asNonNegInt(raw: unknown, fallback: number): number {
  const n = typeof raw === "number" ? raw : Number(raw)
  return Number.isFinite(n) && n >= 0 ? Math.floor(n) : fallback
}

function parseJob(raw: unknown): ScheduleJobSpec | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null
  const obj = raw as Record<string, unknown>
  const id = typeof obj["id"] === "string" ? obj["id"].trim() : ""
  const goal = typeof obj["goal"] === "string" ? obj["goal"].trim() : ""
  if (!id || !goal) return null
  const everyMs = asPositiveInt(obj["everyMs"], 3_600_000)
  const cooldownMs = asNonNegInt(obj["cooldownMs"], everyMs)
  const maxSteps = asPositiveInt(obj["maxSteps"], 3)
  const deadlineRaw = obj["deadlineMs"]
  const deadlineMs =
    deadlineRaw === null || deadlineRaw === undefined
      ? 120_000
      : asPositiveInt(deadlineRaw, 120_000)
  const quietSuccess =
    obj["quietSuccess"] === undefined ? true : Boolean(obj["quietSuccess"])
  const enabled = obj["enabled"] === undefined ? true : Boolean(obj["enabled"])
  const conversationId =
    typeof obj["conversationId"] === "string" && obj["conversationId"].trim()
      ? obj["conversationId"].trim()
      : undefined
  return {
    id,
    everyMs,
    goal,
    ...(conversationId ? { conversationId } : {}),
    cooldownMs,
    maxSteps,
    deadlineMs,
    quietSuccess,
    enabled,
  }
}

export function parseScheduleJobsJson(text: string): readonly ScheduleJobSpec[] {
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    return []
  }
  if (!Array.isArray(parsed)) return []
  const jobs: ScheduleJobSpec[] = []
  for (const item of parsed) {
    const job = parseJob(item)
    if (job) jobs.push(job)
  }
  return jobs
}

export function loadScheduleJobsFromPath(path: string): readonly ScheduleJobSpec[] {
  try {
    const text = readFileSync(path, "utf8")
    return parseScheduleJobsJson(text)
  } catch {
    return []
  }
}

export interface ScheduleWorkerConfig {
  readonly enabled: boolean
  readonly tickMs: number
  readonly jobs: readonly ScheduleJobSpec[]
  /** When true, defer fires while any injectable main-queue busy signal is set. */
  readonly deferWhenMainBusy: boolean
}

export function parseScheduleWorkerConfig(
  env: NodeJS.ProcessEnv = process.env,
  cwd: string = process.cwd(),
): ScheduleWorkerConfig {
  const enabled = envTruthy(env["BUTLER_V5_SCHEDULE_ENABLED"])
  const tickMs = asPositiveInt(env["BUTLER_V5_SCHEDULE_TICK_MS"], 60_000)
  const deferWhenMainBusy = envTruthy(env["BUTLER_V5_SCHEDULE_DEFER_WHEN_BUSY"])
  const inline = (env["BUTLER_V5_SCHEDULE_JOBS"] ?? "").trim()
  const pathRaw = (env["BUTLER_V5_SCHEDULE_JOBS_PATH"] ?? "").trim()
  let jobs: readonly ScheduleJobSpec[] = []
  if (inline) {
    jobs = parseScheduleJobsJson(inline)
  } else if (pathRaw) {
    jobs = loadScheduleJobsFromPath(resolve(cwd, pathRaw))
  } else {
    jobs = loadScheduleJobsFromPath(resolve(cwd, "config/schedule-jobs.json"))
  }
  return { enabled, tickMs, jobs, deferWhenMainBusy }
}

export function isScheduleEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return envTruthy(env["BUTLER_V5_SCHEDULE_ENABLED"])
}
