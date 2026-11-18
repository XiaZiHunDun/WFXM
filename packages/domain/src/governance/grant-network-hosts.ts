import { isMcpCapability } from "./types.js"

/** Extra outbound hosts merged into ScopedGrant (comma/space separated). */
export function parseGrantNetworkHostsFromEnv(
  env: Readonly<Record<string, string | undefined>>,
): readonly string[] {
  const raw = (env["BUTLER_V5_GRANT_NETWORK_HOSTS"] ?? "").trim()
  if (!raw) return []
  return raw
    .split(/[,\s]+/)
    .map((part) => part.trim().toLowerCase())
    .filter((part) => part.length > 0)
}

export function hostnameFromHttpUrl(url: string): string | undefined {
  const trimmed = url.trim()
  if (!trimmed) return undefined
  try {
    return new URL(trimmed).hostname.toLowerCase()
  } catch {
    return undefined
  }
}

export function mcpServerHostnameFromEnv(
  env: Readonly<Record<string, string | undefined>>,
): string | undefined {
  return hostnameFromHttpUrl(env["BUTLER_V5_MCP_URL"] ?? "")
}

/** External API hosts reached by stdio MCP subprocesses (not BUTLER_V5_MCP_URL). */
export function mcpCapabilityOutboundHosts(capability: string): readonly string[] | undefined {
  if (capability.startsWith("mcp_todoist_")) {
    return ["api.todoist.com"]
  }
  if (capability.startsWith("mcp_firecrawl_")) {
    return ["api.firecrawl.dev"]
  }
  if (capability.startsWith("mcp_github_")) {
    return ["api.github.com"]
  }
  return undefined
}

export function mergeGrantNetworkHosts(
  ...groups: readonly (readonly string[] | undefined)[]
): readonly string[] | undefined {
  const merged = new Set<string>()
  for (const group of groups) {
    if (!group) continue
    for (const host of group) {
      const normalized = host.trim().toLowerCase()
      if (normalized) merged.add(normalized)
    }
  }
  if (merged.size === 0) return undefined
  return [...merged]
}

/** Resolve networkHosts written into ScopedGrant at approval time. */
export function resolveGrantNetworkHosts(input: {
  readonly capability: string
  readonly wechatHosts?: readonly string[]
  readonly env?: Readonly<Record<string, string | undefined>>
}): readonly string[] | undefined {
  const env = input.env ?? {}
  const extra = parseGrantNetworkHostsFromEnv(env)

  if (input.capability === "send_wechat_file") {
    return mergeGrantNetworkHosts(input.wechatHosts, extra)
  }

  if (isMcpCapability(input.capability)) {
    const mcpHost = mcpServerHostnameFromEnv(env)
    const outbound = mcpCapabilityOutboundHosts(input.capability)
    return mergeGrantNetworkHosts(mcpHost ? [mcpHost] : undefined, outbound, extra)
  }

  return mergeGrantNetworkHosts(extra)
}
