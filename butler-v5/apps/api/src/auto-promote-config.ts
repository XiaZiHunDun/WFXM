/**
 * G4: auto-promote env config + parser (§12).
 * Opt-in (BUTLER_V5_AUTO_PROMOTE_ENABLED=1); defaults: 3d promote window, 6h interval, 500 batch limit, 7d rollback window.
 */

export interface AutoPromoteConfig {
  readonly enabled: boolean
  readonly windowMs: number // candidate age >= windowMs 才 promote
  readonly sweepLimit: number // per-tick batch limit
  readonly sweepIntervalMs: number // sweeper tick interval
  readonly rollbackWindowMs: number // post-promote owner rollback window
}

function parsePositiveInt(raw: string | undefined, fallback: number): number {
  if (!raw) return fallback
  const n = Number.parseInt(raw, 10)
  return Number.isFinite(n) && n > 0 ? n : fallback
}

const DEFAULT_WINDOW_DAYS = 3
const DEFAULT_INTERVAL_HOURS = 6
const DEFAULT_SWEEP_LIMIT = 500
const DEFAULT_ROLLBACK_WINDOW_DAYS = 7

export function parseAutoPromoteConfig(env: NodeJS.ProcessEnv): AutoPromoteConfig {
  return {
    enabled: env["BUTLER_V5_AUTO_PROMOTE_ENABLED"] === "1",
    windowMs:
      parsePositiveInt(env["BUTLER_V5_AUTO_PROMOTE_WINDOW_DAYS"], DEFAULT_WINDOW_DAYS) *
      24 *
      3_600_000,
    sweepLimit: parsePositiveInt(env["BUTLER_V5_AUTO_PROMOTE_SWEEP_LIMIT"], DEFAULT_SWEEP_LIMIT),
    sweepIntervalMs:
      parsePositiveInt(
        env["BUTLER_V5_AUTO_PROMOTE_SWEEP_INTERVAL_HOURS"],
        DEFAULT_INTERVAL_HOURS,
      ) * 3_600_000,
    rollbackWindowMs:
      parsePositiveInt(
        env["BUTLER_V5_AUTO_PROMOTE_ROLLBACK_WINDOW_DAYS"],
        DEFAULT_ROLLBACK_WINDOW_DAYS,
      ) *
      24 *
      3_600_000,
  }
}
