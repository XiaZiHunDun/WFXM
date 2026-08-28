/**
 * Sandbox profile names and Grant binding helpers (A8).
 *
 * Provider default isolation is `workspace-write-network-deny` when
 * bubblewrap is enabled. Elevating to network-allow must be written on
 * a short-lived, non-delegable ScopedGrant (`sandboxProfile` column).
 */
export const SANDBOX_PROFILE_NETWORK_DENY = "workspace-write-network-deny" as const
export const SANDBOX_PROFILE_NETWORK_ALLOW = "workspace-write-network-allow" as const
export {
  SANDBOX_PROFILE_NETWORK_ALLOWLIST,
} from "@butler/domain/governance/network-allowlist.js"

import { SANDBOX_PROFILE_NETWORK_ALLOWLIST } from "@butler/domain/governance/network-allowlist.js"

export type SandboxProfileName =
  | typeof SANDBOX_PROFILE_NETWORK_DENY
  | typeof SANDBOX_PROFILE_NETWORK_ALLOW
  | typeof SANDBOX_PROFILE_NETWORK_ALLOWLIST

export const KNOWN_SANDBOX_PROFILES: readonly SandboxProfileName[] = [
  SANDBOX_PROFILE_NETWORK_DENY,
  SANDBOX_PROFILE_NETWORK_ALLOW,
  SANDBOX_PROFILE_NETWORK_ALLOWLIST,
]

export function parseSandboxProfileName(raw: unknown): SandboxProfileName | null {
  if (typeof raw !== "string") return null
  const trimmed = raw.trim()
  if ((KNOWN_SANDBOX_PROFILES as readonly string[]).includes(trimmed)) {
    return trimmed as SandboxProfileName
  }
  return null
}

/**
 * Profile to stamp on an approved ScopedGrant.
 * - Explicit allowlist → network-allowlist (P2b)
 * - Explicit Owner elevation → network-allow
 * - command / MCP capabilities → bind default deny ceiling (not elevation)
 * - other capabilities → null (provider default)
 */
export function sandboxProfileForApprovedCapability(
  capability: string,
  options: {
    readonly elevateNetwork?: boolean
    readonly networkAllowlist?: readonly string[]
  } = {},
): string | null {
  if (options.networkAllowlist && options.networkAllowlist.length > 0) {
    return SANDBOX_PROFILE_NETWORK_ALLOWLIST
  }
  if (options.elevateNetwork) return SANDBOX_PROFILE_NETWORK_ALLOW
  if (
    capability === "run_command" ||
    capability === "read_file" ||
    capability === "write_file" ||
    capability.startsWith("mcp_")
  ) {
    return SANDBOX_PROFILE_NETWORK_DENY
  }
  return null
}

export function isSandboxEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return (env["BUTLER_V5_SANDBOX"] ?? "").trim() === "bubblewrap"
}
