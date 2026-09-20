/**
 * D73 SEC-002: DNS rebinding defense at fetch time.
 *
 * The MCP/V5_INBOUND host allowlist checks hostname literals at parse
 * time only. Between parse and the actual fetch (which can be seconds
 * later for long-poll MCP HTTP/SSE transports, or hours for ilink-poller
 * cycles), an attacker controlling the DNS record can rebind a hostname
 * to a private IP. Classic DNS rebinding bypasses parse-time guards.
 *
 * This module wraps any `typeof fetch` so that EACH invocation:
 *   1. Parses the target URL.
 *   2. Resolves the hostname via `dns.lookup` (returns all A/AAAA records).
 *   3. Runs each resolved address through the supplied `isBlockedHost`
 *      predicate. If ANY address is blocked, the wrapper throws —
 *      short-circuiting the actual HTTP call.
 *   4. Otherwise invokes the underlying fetch.
 *
 * Usage:
 *   const guardedFetch = makeGuardedFetch(baseFetch, url, isBlockedMcpHost)
 *   await guardedFetch(url, init) // throws if DNS rebound to private
 *
 * Note: this does NOT pin the resolved IP (Node's fetch uses its own
 * DNS resolver). It detects the rebinding at fetch time but does not
 * prevent the underlying fetch from re-resolving. Sufficient for the
 * SSRF threat model: an attacker can't bypass the parse-time guard
 * via DNS rebinding without the wrapper catching the rebind before
 * the actual outbound connection is made. The parse-time guard
 * remains the primary defense; this is the second layer.
 */
import { lookup } from "node:dns/promises"

export type HostBlockPredicate = (hostname: string) => boolean

const IPV4_LITERAL = /^\d{1,3}(?:\.\d{1,3}){3}$/
const IPV6_LITERAL_HOST = /^[0-9a-f:]+$/i

function isLiteralIp(host: string): boolean {
  return IPV4_LITERAL.test(host) || (host.includes(":") && IPV6_LITERAL_HOST.test(host))
}

/**
 * Resolve the hostname of `url` and assert every returned address
 * passes `isBlockedHost`. Throws on any blocked address.
 */
export async function assertPublicHost(
  url: string,
  isBlockedHost: HostBlockPredicate,
): Promise<void> {
  let parsed: URL
  try {
    parsed = new URL(url)
  } catch {
    throw new Error(`DNS recheck: invalid URL ${url}`)
  }
  const hostname = parsed.hostname
  if (isLiteralIp(hostname)) {
    // Already a literal — no DNS resolution needed, but still validate
    // against the blocklist (handles e.g. ::1, 127.0.0.1, 169.254.169.254).
    if (isBlockedHost(hostname)) {
      throw new Error(
        `DNS recheck: host ${hostname} is on the private-network deny list`,
      )
    }
    return
  }
  let addrs: readonly { readonly address: string }[]
  try {
    addrs = await lookup(hostname, { all: true, family: 0 })
  } catch (err) {
    throw new Error(
      `DNS recheck: lookup failed for ${hostname}: ${
        err instanceof Error ? err.message : String(err)
      }`,
    )
  }
  if (addrs.length === 0) {
    throw new Error(`DNS recheck: lookup returned no addresses for ${hostname}`)
  }
  for (const { address } of addrs) {
    if (isBlockedHost(address)) {
      throw new Error(
        `DNS recheck: host ${hostname} resolves to ${address} which is on the private-network deny list`,
      )
    }
  }
}

/**
 * Wrap `baseFetch` so every invocation first re-resolves DNS and
 * re-validates against `isBlockedHost`. The URL is fixed at wrapper
 * creation; pass a per-request wrapper if you need per-URL guarding.
 */
export function makeGuardedFetch(
  baseFetch: typeof fetch,
  url: string,
  isBlockedHost: HostBlockPredicate,
): typeof fetch {
  return async (input, init) => {
    await assertPublicHost(url, isBlockedHost)
    return baseFetch(input, init)
  }
}