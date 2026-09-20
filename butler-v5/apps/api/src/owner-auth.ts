import type { Context } from "hono"

const LOOPBACK = new Set(["127.0.0.1", "::1", "::ffff:127.0.0.1"])

/** True for localhost / loopback client addresses. */
export function isLoopbackAddress(address: string | undefined): boolean {
  if (!address) return false
  const normalized = address.toLowerCase()
  if (LOOPBACK.has(normalized)) return true
  if (normalized.startsWith("::ffff:127.")) return true
  return false
}

function remoteAddressFromContext(c: Context): string | undefined {
  try {
    const bindings = (c.env as { server?: unknown }).server ?? c.env
    const incoming = (bindings as { incoming?: { socket?: { remoteAddress?: string } } })
      .incoming
    return incoming?.socket?.remoteAddress
  } catch (err) {
    // D74 T5 (audit #19 CQ-021 partial): observability for the silent
    // catch — the auth bypass relies on remoteAddress being parsed, so
    // a parse failure should leave a debug-level trail. Worst case the
    // route falls back to caller-bind (existing behavior).
    // eslint-disable-next-line no-console -- intentional debug log when no logger injected
    console.error("[owner-auth] remoteAddress parse failed:", err)
    return undefined
  }
}

/** Used by tests to assert auth policy without a real socket. */
export function ownerAuthorizedFromAddress(address: string | undefined): boolean {
  if (address !== undefined) return isLoopbackAddress(address)
  // vitest app.request() has no socket; allow in test runs only.
  return (process.env["VITEST"] ?? "").trim() !== ""
}

/**
 * Owner API is loopback-only — no separate bearer token.
 * Matches product boundary: local control surface, not exposed to LAN/WAN.
 *
 * D63 T4 (audit #9 F-07): reject any request that arrives with an
 * X-Forwarded-For or X-Real-IP header. The default loopback check
 * trusts the immediate socket peer address. If operator runs butler-v5
 * behind a reverse proxy (nginx/caddy) on 127.0.0.1:3000, the proxy's
 * socket remoteAddress is 127.0.0.1 — ownerAuthorized would return
 * true for ANY external request that traverses the proxy. The proxy's
 * own IP sits in X-Forwarded-For; if it's present, treat the request
 * as not loopback-originated (fail-CLOSED). Explicit trust-proxy config
 * with X-Forwarded-For chain handling is the longer-term fix; deferred
 * — D63 ships the defense-in-depth reject instead.
 */
export function ownerAuthorized(c: Context): boolean {
  if (c.req.header("x-forwarded-for") !== undefined) return false
  if (c.req.header("x-real-ip") !== undefined) return false
  return ownerAuthorizedFromAddress(remoteAddressFromContext(c))
}
