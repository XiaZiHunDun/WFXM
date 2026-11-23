/**
 * Opt-in weekly digest config.
 *
 * BUTLER_V5_WEEKLY_DIGEST_ENABLED=1
 * BUTLER_V5_WEEKLY_DIGEST_TO=<owner wechat user id>
 * BUTLER_V5_WEEKLY_DIGEST_WEEKDAY=1   # 0=周日 … 6=周六，默认周一
 * BUTLER_V5_WEEKLY_DIGEST_TIME=09:00  # Asia/Shanghai
 * BUTLER_V5_WEEKLY_DIGEST_TICK_MS=60000
 */
import { envTruthy } from "./env-util.js"

const DEFAULT_TICK_MS = 60_000
const DEFAULT_WEEKDAY = 1
const DEFAULT_HOUR = 9
const DEFAULT_MINUTE = 0

const TIME_PATTERN = /^(\d{1,2}):(\d{2})$/

function boundedInt(raw: unknown, fallback: number, min: number, max: number): number {
  const n = typeof raw === "number" ? raw : Number(raw)
  if (!Number.isFinite(n)) return fallback
  return Math.min(Math.max(Math.floor(n), min), max)
}

function parseTime(raw: string | undefined): { readonly hour: number; readonly minute: number } {
  const match = TIME_PATTERN.exec((raw ?? "").trim())
  if (!match) return { hour: DEFAULT_HOUR, minute: DEFAULT_MINUTE }
  const hour = Number(match[1])
  const minute = Number(match[2])
  if (hour > 23 || minute > 59) return { hour: DEFAULT_HOUR, minute: DEFAULT_MINUTE }
  return { hour, minute }
}

export interface WeeklyDigestConfig {
  readonly enabled: boolean
  /** Recipient wechat user id; null when the operator has not configured one. */
  readonly to: string | null
  /** 0=周日 … 6=周六 (Asia/Shanghai). */
  readonly weekday: number
  readonly hour: number
  readonly minute: number
  readonly tickMs: number
}

export function isWeeklyDigestEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return envTruthy(env["BUTLER_V5_WEEKLY_DIGEST_ENABLED"])
}

export function parseWeeklyDigestConfig(env: NodeJS.ProcessEnv = process.env): WeeklyDigestConfig {
  const time = parseTime(env["BUTLER_V5_WEEKLY_DIGEST_TIME"])
  const to = (env["BUTLER_V5_WEEKLY_DIGEST_TO"] ?? "").trim()
  return {
    enabled: isWeeklyDigestEnabled(env),
    to: to || null,
    weekday: boundedInt(env["BUTLER_V5_WEEKLY_DIGEST_WEEKDAY"], DEFAULT_WEEKDAY, 0, 6),
    hour: time.hour,
    minute: time.minute,
    tickMs: boundedInt(env["BUTLER_V5_WEEKLY_DIGEST_TICK_MS"], DEFAULT_TICK_MS, 5_000, 600_000),
  }
}
