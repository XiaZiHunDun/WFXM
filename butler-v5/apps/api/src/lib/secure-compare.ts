/**
 * D73 SEC-004: timing-safe string comparison helpers.
 *
 * Promoted from `channel-inbound.ts:181-186` (added in D72 T3 audit #18
 * SEC-001 for Telegram webhook). The channel-inbound shared secret and
 * the inbound shared secret were still compared with `!==` — both
 * asymmetric with Telegram's now-closed timing-safe compare. This
 * module is the single source of truth for all secret-bearing string
 * comparisons in apps/api.
 *
 * Conventions:
 *   - `timingSafeEqualStrings(a, b)`: equal-length inputs required.
 *     Throws when lengths differ (mirrors Node's `crypto.timingSafeEqual`).
 *   - `safeCompareTrimmedSecrets(expected, provided)`: trims both sides,
 *     returns false on length mismatch without throwing, then
 *     timing-safe compares. Use this for any user-supplied vs
 *     configured-secret check where lengths can vary.
 */
import { timingSafeEqual } from "node:crypto"

export function timingSafeEqualStrings(a: string, b: string): boolean {
  const bufA = Buffer.from(a, "utf8")
  const bufB = Buffer.from(b, "utf8")
  // timingSafeEqual throws if lengths differ; caller gated above.
  return timingSafeEqual(bufA, bufB)
}

/**
 * Trim both strings, short-circuit false on length mismatch (without
 * leaking length via throw), then constant-time compare. Caller is
 * responsible for handling the boolean result.
 */
export function safeCompareTrimmedSecrets(expected: string, provided: string): boolean {
  const a = expected.trim()
  const b = provided.trim()
  if (a.length !== b.length) return false
  if (a.length === 0) return false
  return timingSafeEqualStrings(a, b)
}