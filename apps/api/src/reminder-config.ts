/**
 * Opt-in reminder config.
 *
 * BUTLER_V5_REMINDERS_ENABLED=1
 * BUTLER_V5_REMINDERS_TICK_MS=30000
 * BUTLER_V5_REMINDERS_MAX_PER_OWNER=20
 */
import { envTruthy } from "./env-util.js"

const DEFAULT_TICK_MS = 30_000
const DEFAULT_MAX_PER_OWNER = 20

function boundedInt(raw: unknown, fallback: number, min: number, max: number): number {
  const n = typeof raw === "number" ? raw : Number(raw)
  if (!Number.isFinite(n)) return fallback
  return Math.min(Math.max(Math.floor(n), min), max)
}

export interface ReminderConfig {
  readonly enabled: boolean
  readonly tickMs: number
  readonly maxPerOwner: number
}

export function isRemindersEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return envTruthy(env["BUTLER_V5_REMINDERS_ENABLED"])
}

export function parseReminderConfig(env: NodeJS.ProcessEnv = process.env): ReminderConfig {
  return {
    enabled: isRemindersEnabled(env),
    tickMs: boundedInt(env["BUTLER_V5_REMINDERS_TICK_MS"], DEFAULT_TICK_MS, 5_000, 300_000),
    maxPerOwner: boundedInt(
      env["BUTLER_V5_REMINDERS_MAX_PER_OWNER"],
      DEFAULT_MAX_PER_OWNER,
      1,
      100,
    ),
  }
}
