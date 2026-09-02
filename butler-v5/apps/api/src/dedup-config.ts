/**
 * G2: candidate dedup config — env-driven threshold (default 0.85; 0 = off).
 * Mirrors parseCandidateExpiresSweeperConfig pattern (D40).
 */
import { parsePositiveInt } from "./env-util.js"

export interface DedupConfig {
  readonly enabled: boolean // threshold > 0
  readonly threshold: number
  readonly recentMs: number // default 90d
  readonly limit: number // default 50
}

function parseFloatSafe(raw: string | undefined, fallback: number): number {
  if (!raw) return fallback
  const n = Number.parseFloat(raw)
  return Number.isFinite(n) && n >= 0 ? n : fallback
}

export function parseDedupConfig(env: NodeJS.ProcessEnv): DedupConfig {
  const threshold = parseFloatSafe(env["BUTLER_V5_MEMORY_DEDUP_THRESHOLD"], 0.85)
  return {
    enabled: threshold > 0,
    threshold,
    recentMs: parsePositiveInt(env["BUTLER_V5_MEMORY_DEDUP_RECENT_MS"], 90 * 24 * 3_600_000),
    limit: parsePositiveInt(env["BUTLER_V5_MEMORY_DEDUP_LIMIT"], 50),
  }
}
