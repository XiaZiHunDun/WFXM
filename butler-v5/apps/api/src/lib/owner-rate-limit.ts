/**
 * D70 T4 (audit #11 SEC-002): in-memory sliding-window throttle for
 * owner routes. Previously /v1/owner/* had no rate limit — a compromised
 * loopback caller or runaway local script could flood expensive endpoints
 * (audit/fatigue/replay caps batch at 1000 ids; documents/memories/
 * project-knowledge have no batch cap at all). Mirror the
 * `wechat-sweeper-notify.ts` per-process throttle pattern.
 *
 * Configuration: BUTLER_V5_OWNER_RATE_LIMIT_WINDOW_MS (default 60_000),
 * BUTLER_V5_OWNER_RATE_LIMIT_MAX (default 120). When window is 0 the
 * throttle is disabled (escape hatch for tests + benchmark scripts).
 *
 * Scope: per (remoteAddress-or-VITEST-gate) sliding window. Lost on
 * process restart, which is fine — the loopback control surface only
 * serves local operators and the cap is generous enough that a fresh
 * start is a non-event.
 */

const OWNER_RATE_WINDOW_MS_DEFAULT = 60_000
const OWNER_RATE_MAX_DEFAULT = 120

function ownerRateLimitWindowMs(env: NodeJS.ProcessEnv): number {
  const raw = env["BUTLER_V5_OWNER_RATE_LIMIT_WINDOW_MS"]
  if (raw === undefined) return OWNER_RATE_WINDOW_MS_DEFAULT
  const n = Number.parseInt(raw, 10)
  return Number.isFinite(n) && n >= 0 ? n : OWNER_RATE_WINDOW_MS_DEFAULT
}

function ownerRateLimitMax(env: NodeJS.ProcessEnv): number {
  const raw = env["BUTLER_V5_OWNER_RATE_LIMIT_MAX"]
  if (raw === undefined) return OWNER_RATE_MAX_DEFAULT
  const n = Number.parseInt(raw, 10)
  return Number.isFinite(n) && n > 0 ? n : OWNER_RATE_MAX_DEFAULT
}

const recentRequestMs: Map<string, number[]> = new Map()

export function resetOwnerRateLimitForTests(): void {
  recentRequestMs.clear()
}

export function _peekOwnerRateLimitForTests(key: string): readonly number[] {
  return recentRequestMs.get(key) ?? []
}

/**
 * Check whether the next request from `key` is allowed. Returns true
 * when the request should proceed; false when the cap has been hit
 * within the sliding window. Mutates `recentRequestMs[key]` (clears
 * expired timestamps and appends the new one).
 */
export function tryAcquireOwnerSlot(key: string, env: NodeJS.ProcessEnv): boolean {
  const windowMs = ownerRateLimitWindowMs(env)
  if (windowMs === 0) return true
  const max = ownerRateLimitMax(env)
  const now = Date.now()
  const cutoff = now - windowMs
  const prior = (recentRequestMs.get(key) ?? []).filter(ts => ts > cutoff)
  if (prior.length >= max) {
    recentRequestMs.set(key, prior)
    return false
  }
  prior.push(now)
  recentRequestMs.set(key, prior)
  return true
}
