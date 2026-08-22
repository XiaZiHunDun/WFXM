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
  } catch {
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
 */
export function ownerAuthorized(c: Context): boolean {
  return ownerAuthorizedFromAddress(remoteAddressFromContext(c))
}
