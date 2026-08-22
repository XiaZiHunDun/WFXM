import { createHash } from "node:crypto"
import { domainToASCII } from "node:url"

export const SANDBOX_PROFILE_NETWORK_ALLOWLIST = "workspace-write-network-allowlist" as const

export const MAX_NETWORK_ALLOWLIST_ENTRIES = 8

export const DEFAULT_NETWORK_ALLOWLIST_PORT = 443

const PRIVATE_IPV4_PREFIXES = [
  "127.",
  "10.",
  "192.168.",
] as const

function isPrivateIpv4Host(host: string): boolean {
  if (host === "localhost") return true
  for (const prefix of PRIVATE_IPV4_PREFIXES) {
    if (host.startsWith(prefix)) return true
  }
  const parts = host.split(".")
  if (parts.length === 4 && parts.every((p) => /^\d+$/.test(p))) {
    const second = Number(parts[1])
    if (parts[0] === "172" && second >= 16 && second <= 31) return true
    if (host === "0.0.0.0") return true
  }
  return false
}

function splitHostPort(raw: string): { readonly host: string; readonly port: number } | null {
  const trimmed = raw.trim()
  if (!trimmed) return null
  if (trimmed.includes("/")) return null
  if (trimmed === "*" || trimmed.startsWith("*.")) return null
  const lastColon = trimmed.lastIndexOf(":")
  if (lastColon <= 0) {
    return { host: trimmed, port: DEFAULT_NETWORK_ALLOWLIST_PORT }
  }
  const hostPart = trimmed.slice(0, lastColon)
  const portPart = trimmed.slice(lastColon + 1)
  if (!hostPart || hostPart.includes(":")) return null
  if (!/^\d+$/.test(portPart)) return null
  const port = Number(portPart)
  if (!Number.isInteger(port) || port < 1 || port > 65535) return null
  return { host: hostPart, port }
}

function normalizeHost(host: string): string | null {
  const lower = host.trim().toLowerCase()
  if (!lower || lower.length > 253) return null
  if (lower.includes("..")) return null
  try {
    const ascii = domainToASCII(lower)
    if (!ascii || ascii.includes("..")) return null
    return ascii.toLowerCase()
  } catch {
    return null
  }
}

export function normalizeNetworkAllowlistEntry(
  raw: string,
): { readonly ok: true; readonly value: string } | { readonly ok: false; readonly reason: string } {
  const split = splitHostPort(raw)
  if (!split) {
    return { ok: false, reason: `invalid allowlist entry: ${raw}` }
  }
  const host = normalizeHost(split.host)
  if (!host) {
    return { ok: false, reason: `invalid host in allowlist entry: ${raw}` }
  }
  return { ok: true, value: `${host}:${split.port}` }
}

export function validateNetworkAllowlist(
  entries: readonly string[],
  options: { readonly allowPrivateEgress?: boolean } = {},
): { readonly ok: true; readonly normalized: readonly string[] } | { readonly ok: false; readonly reason: string } {
  if (entries.length === 0) {
    return { ok: false, reason: "networkAllowlist must not be empty" }
  }
  if (entries.length > MAX_NETWORK_ALLOWLIST_ENTRIES) {
    return {
      ok: false,
      reason: `networkAllowlist exceeds max ${MAX_NETWORK_ALLOWLIST_ENTRIES} entries`,
    }
  }
  const normalized: string[] = []
  const seen = new Set<string>()
  for (const entry of entries) {
    const parsed = normalizeNetworkAllowlistEntry(entry)
    if (!parsed.ok) return parsed
    if (seen.has(parsed.value)) continue
    const host = parsed.value.split(":")[0] ?? ""
    if (!options.allowPrivateEgress && isPrivateIpv4Host(host)) {
      return {
        ok: false,
        reason: `private or loopback host not allowed without opt-in: ${host}`,
      }
    }
    seen.add(parsed.value)
    normalized.push(parsed.value)
  }
  return { ok: true, normalized }
}

export function hashNetworkAllowlistForAudit(entries: readonly string[]): string {
  return createHash("sha256").update(entries.join("\n")).digest("hex").slice(0, 16)
}

export function hostnamesFromNetworkAllowlist(
  entries: readonly string[],
): readonly string[] {
  const hosts = new Set<string>()
  for (const entry of entries) {
    const host = entry.split(":")[0]?.trim().toLowerCase()
    if (host) hosts.add(host)
  }
  return [...hosts]
}

export function envAllowPrivateEgress(
  env: Readonly<Record<string, string | undefined>> = process.env,
): boolean {
  const raw = (env["BUTLER_V5_SANDBOX_ALLOW_PRIVATE_EGRESS"] ?? "").trim().toLowerCase()
  return raw === "1" || raw === "true" || raw === "yes" || raw === "on"
}

export type SandboxNetworkMode = "binary" | "allowlist"

export function resolveSandboxNetworkMode(
  env: Readonly<Record<string, string | undefined>> = process.env,
): SandboxNetworkMode {
  const raw = (env["BUTLER_V5_SANDBOX_NETWORK_MODE"] ?? "binary").trim().toLowerCase()
  return raw === "allowlist" ? "allowlist" : "binary"
}

export type SandboxEgressIsolation = "proxy" | "slirp"

/** P2c = host-network egress proxy; P2d = slirp netns + iptables hard isolation. */
export function resolveSandboxEgressIsolation(
  env: Readonly<Record<string, string | undefined>> = process.env,
): SandboxEgressIsolation {
  const raw = (env["BUTLER_V5_SANDBOX_EGRESS_ISOLATION"] ?? "proxy").trim().toLowerCase()
  return raw === "slirp" ? "slirp" : "proxy"
}

export function destinationKey(host: string, port: number): string {
  const normalized = normalizeHost(host)
  if (!normalized) return `${host.toLowerCase()}:${port}`
  return `${normalized}:${port}`
}

export function isDestinationAllowedInNetworkAllowlist(
  host: string,
  port: number,
  allowlist: readonly string[],
): boolean {
  const key = destinationKey(host, port)
  const allowed = new Set(allowlist.map((entry) => entry.toLowerCase()))
  return allowed.has(key)
}
