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

/**
 * D61 T4 (audit #1 F-02): dedup threshold is a Jaccard similarity in [0, 1].
 * Anything > 1.0 disables dedup (can never match), so clamp the upper bound
 * to 1.0 to surface operator typos (e.g. `2.0` for `0.85`) instead of
 * silently turning the feature off.
 */
function parseDedupThreshold(raw: string | undefined, fallback: number): number {
  const n = parseFloatSafe(raw, fallback)
  return n > 1 ? fallback : n
}

export function parseDedupConfig(env: NodeJS.ProcessEnv): DedupConfig {
  const threshold = parseDedupThreshold(env["BUTLER_V5_MEMORY_DEDUP_THRESHOLD"], 0.85)
  return {
    enabled: threshold > 0,
    threshold,
    recentMs: parsePositiveInt(env["BUTLER_V5_MEMORY_DEDUP_RECENT_MS"], 90 * 24 * 3_600_000),
    limit: parsePositiveInt(env["BUTLER_V5_MEMORY_DEDUP_LIMIT"], 50),
  }
}
