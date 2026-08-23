/** Prefix for MCP-discovered capabilities (opt-in via BUTLER_V5_MCP_ENABLED). */
export const MCP_CAPABILITY_PREFIX = "mcp_"

export type McpRiskLevel = "low" | "medium" | "high"

export interface McpGrantScope {
  readonly serverId: string
  readonly toolName: string
}

export interface McpToolCapability {
  readonly capability: string
  readonly toolName: string
  readonly serverId?: string
}

export type McpAuditPolicy = "full" | "summary"

export interface McpProviderMetadata {
  readonly serverId: string
  readonly defaultRisk: McpRiskLevel
  readonly defaultSandboxProfile: string
  readonly auditPolicy: McpAuditPolicy
}

export const DEFAULT_MCP_SANDBOX_PROFILE = "workspace-write-network-deny"
export const DEFAULT_MCP_RISK: McpRiskLevel = "high"
export const DEFAULT_MCP_AUDIT_POLICY: McpAuditPolicy = "summary"

export function isMcpCapability(capability: string): boolean {
  return capability.startsWith(MCP_CAPABILITY_PREFIX)
}

export function normalizeMcpServerId(serverId: string): string {
  return serverId.trim().toLowerCase()
}

export function normalizeMcpToolName(toolName: string): string {
  return toolName.trim()
}

export function toMcpCapabilityName(toolName: string): string | null {
  const trimmed = normalizeMcpToolName(toolName)
  if (!trimmed) {
    return null
  }
  if (trimmed.startsWith(MCP_CAPABILITY_PREFIX)) {
    return trimmed
  }
  return `${MCP_CAPABILITY_PREFIX}${trimmed}`
}

/** v4-style namespacing: `mcp_{serverId}_{toolName}` for multi-server manifests. */
export function toMcpCapabilityNameForServer(serverId: string, toolName: string): string | null {
  const sid = normalizeMcpServerId(serverId)
  const tool = normalizeMcpToolName(toolName)
  if (!sid || !tool) {
    return null
  }
  return `${MCP_CAPABILITY_PREFIX}${sid}_${tool}`
}

export function parseMcpCapability(
  capability: string,
  serverIds: readonly string[] = [],
): McpToolCapability | null {
  if (!isMcpCapability(capability)) {
    return null
  }
  const rest = capability.slice(MCP_CAPABILITY_PREFIX.length)
  if (!rest) {
    return null
  }
  const normalizedIds = [...serverIds]
    .map((id) => normalizeMcpServerId(id))
    .filter((id) => id.length > 0)
    .sort((a, b) => b.length - a.length)
  for (const serverId of normalizedIds) {
    const prefix = `${serverId}_`
    if (rest.toLowerCase().startsWith(prefix)) {
      const toolName = normalizeMcpToolName(rest.slice(prefix.length))
      if (!toolName) {
        return null
      }
      return { capability, toolName, serverId }
    }
  }
  const toolName = normalizeMcpToolName(rest)
  if (!toolName) {
    return null
  }
  return { capability, toolName }
}

export function resolveMcpServerIdFromCapability(
  capability: string,
  serverIds: readonly string[],
): string | undefined {
  const parsed = parseMcpCapability(capability, serverIds)
  return parsed?.serverId
}

export function defaultMcpProviderMetadata(serverId: string): McpProviderMetadata {
  return {
    serverId: normalizeMcpServerId(serverId),
    defaultRisk: DEFAULT_MCP_RISK,
    defaultSandboxProfile: DEFAULT_MCP_SANDBOX_PROFILE,
    auditPolicy: DEFAULT_MCP_AUDIT_POLICY,
  }
}

export function normalizeMcpGrantScope(input: {
  readonly serverId: string
  readonly toolName: string
}): McpGrantScope | null {
  const toolName = normalizeMcpToolName(input.toolName)
  const serverId = normalizeMcpServerId(input.serverId)
  if (!serverId || !toolName) {
    return null
  }
  return { serverId, toolName }
}

/** True when a persisted grant scope is bound to an MCP server (P3). */
export function scopedGrantScopeTargetsMcpServer(
  scope: { readonly mcp?: McpGrantScope },
  serverId: string,
): boolean {
  if (!scope.mcp) {
    return false
  }
  return normalizeMcpServerId(scope.mcp.serverId) === normalizeMcpServerId(serverId)
}

/** Grant scope must cover the requested MCP tool; legacy grants without `mcp` use capabilities only. */
export function grantScopeMatchesMcpTool(
  scope: {
    readonly capabilities: readonly string[]
    readonly mcp?: McpGrantScope
  },
  parsed: McpToolCapability,
): boolean {
  if (!scope.capabilities.includes(parsed.capability)) {
    return false
  }
  if (!scope.mcp) {
    return true
  }
  return normalizeMcpToolName(scope.mcp.toolName) === parsed.toolName
}
