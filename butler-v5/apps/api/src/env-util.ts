/**
 * Shared env parsing conventions for apps/api: booleans and positive integers.
 *
 * Single source of truth so feature toggles parse identically everywhere
 * (previously duplicated per module, which allowed drift e.g. missing "yes").
 */
import { safeCompareTrimmedSecrets } from "./lib/secure-compare.js"

export function envTruthy(raw: string | undefined): boolean {
  if (!raw) return false
  const text = raw.trim().toLowerCase()
  return text === "1" || text === "true" || text === "yes" || text === "on"
}

/**
 * Parse a positive integer from an env value, falling back to `fallback` when
 * the value is missing, not a finite number, or not > 0. Used for the repeated
 * `BUTLER_V5_*_MS` / `*_LIMIT` / `*_DAYS` config knobs (previously a per-module
 * local helper that drifted in name only).
 */
export function parsePositiveInt(raw: string | undefined, fallback: number): number {
  if (!raw) return fallback
  const n = Number.parseInt(raw, 10)
  return Number.isFinite(n) && n > 0 ? n : fallback
}

/**
 * D72 T4 (audit #18 CQ-017): parse `BUTLER_V5_MCP_TIMEOUT_MS` from env,
 * falling back to 30_000 ms. Single source of truth — replaces the 2×
 * duplicated `Number(env[...] ?? 30_000)` pattern that previously lived
 * in mcp-config.ts and tool-boundary.ts.
 *
 * Note: 30_000 constants in `channel-outbound-media.ts` (telegram media
 * upload timeout) and `subagent-worker.ts` (LLM_TIMEOUT_MS) are different
 * surfaces — they intentionally default to 30_000 but do NOT consume the
 * same env knob. Don't extend this helper to those sites.
 */
export function parseMcpTimeoutMs(env: NodeJS.ProcessEnv): number {
  return parsePositiveInt(env["BUTLER_V5_MCP_TIMEOUT_MS"], 30_000)
}

/**
 * D72 T4 (audit #18 CQ-016): shared-secret auth check used by 3 Hono
 * handlers (wechat/inbound, events POST, ws/subscribe). Returns the
 * Hono response on auth failure (401) or null on success. Replaces a
 * 3× duplicated 7-line block.
 *
 * D73 SEC-004: compare with `safeCompareTrimmedSecrets` (timing-safe)
 * — was `!==` since D72 T4; symmetric with Telegram's now-closed
 * timing-safe path. Length mismatch returns false without throwing
 * (timingSafeEqual throws on unequal length).
 */
export function requireInboundSharedSecret(
  env: NodeJS.ProcessEnv,
  headerValue: string | undefined,
): Response | null {
  const expected = (env["BUTLER_V5_INBOUND_SHARED_SECRET"] ?? "").trim()
  if (!expected) {
    return new Response("inbound shared secret not configured", { status: 401 })
  }
  const provided = (headerValue ?? "").trim()
  if (!safeCompareTrimmedSecrets(expected, provided)) {
    return new Response("invalid inbound secret", { status: 401 })
  }
  return null
}
