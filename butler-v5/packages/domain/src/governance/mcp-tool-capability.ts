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
  return mcpProviderMetadataFromManifest({ serverId })
}

/** Resolve provider metadata from manifest server defaults (P3 skeleton). */
export function mcpProviderMetadataFromManifest(input: {
  readonly serverId: string
  readonly defaultRisk?: McpRiskLevel
  readonly defaultSandboxProfile?: string
  readonly auditPolicy?: McpAuditPolicy
}): McpProviderMetadata {
  return {
    serverId: normalizeMcpServerId(input.serverId),
    defaultRisk: input.defaultRisk ?? DEFAULT_MCP_RISK,
    defaultSandboxProfile: input.defaultSandboxProfile ?? DEFAULT_MCP_SANDBOX_PROFILE,
    auditPolicy: input.auditPolicy ?? DEFAULT_MCP_AUDIT_POLICY,
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

/** Grant scope must cover the requested MCP tool; capability match is enforced separately
 * via record.capability === request.capability (D2.2 first-class). Legacy non-MCP grants
 * that omit mcp fall through (legacy compat preserved). */
export function grantScopeMatchesMcpTool(
  scope: {
    readonly mcp?: McpGrantScope
  },
  parsed: McpToolCapability,
): boolean {
  if (!scope.mcp) {
    return true
  }
  return normalizeMcpToolName(scope.mcp.toolName) === parsed.toolName
}

// ---- P3-3: named server/tool registry, untrusted descriptions, remote OAuth ----

/** A server-declared tool entry is scaled up to a concrete registered tool with
 * an authoritative risk + sandbox profile. */
export interface McpServerToolRegistration {
  readonly toolName: string
  readonly capability: string
  readonly risk: McpRiskLevel
  readonly serverId: string
}

export interface McpServerDescriptor {
  readonly id: string
  readonly defaultRisk?: McpRiskLevel
  readonly defaultSandboxProfile?: string
  readonly auditPolicy?: McpAuditPolicy
  readonly transport?: "http" | "sse" | "stdio" | string
  readonly url?: string
  readonly oauthAudience?: string
  readonly tools: readonly { readonly name: string; readonly risk?: McpRiskLevel }[]
}

/**
 * Tool descriptions are untrusted: a server-declared `risk` is ignored and can
 * never lower isolation. The SERVER default (explicit or high) is authoritative.
 */
export function resolveMcpToolRisk(
  server: McpServerDescriptor,
  _tool: { readonly risk?: McpRiskLevel } = {},
): McpRiskLevel {
  return server.defaultRisk ?? DEFAULT_MCP_RISK
}

/** Map a server + its tool names to concrete registered MCP capabilities. */
export function mcpToolsFromServer(server: McpServerDescriptor): readonly McpServerToolRegistration[] {
  const serverId = normalizeMcpServerId(server.id)
  if (!serverId) return []
  return server.tools
    .map((tool) => {
      const capability = toMcpCapabilityNameForServer(serverId, tool.name)
      if (!capability) return null
      return {
        toolName: normalizeMcpToolName(tool.name),
        capability,
        risk: resolveMcpToolRisk(server, tool),
        serverId,
      }
    })
    .filter((reg): reg is McpServerToolRegistration => reg !== null)
}

/**
 * Remote OAuth audience binding: a remote (http/sse) MCP server must declare the
 * expected OAuth `audience` the host will present. A remote server WITHOUT a
 * declared audience is refused OAuth/passthrough token flows (fail-closed).
 */
export function resolveMcpOAuthAudience(server: McpServerDescriptor): string | null {
  if (server.transport !== "http" && server.transport !== "sse") return null
  const raw = (server.oauthAudience ?? "").trim()
  return raw ? raw : null
}

/** Reject model-supplied credential-style args from reaching a remote server
 * unless that server has an explicit OAuth audience binding (no token passthrough). */
const TOKENISH_KEYS = new Set([
  "authorization",
  "api_key",
  "apiKey",
  "bearer",
  "credential",
  "token",
  "password",
  "secret",
  "access_token",
])

export function rejectMcpTokenPassthrough(
  server: McpServerDescriptor,
  args: Readonly<Record<string, unknown>>,
): { readonly ok: true } | { readonly ok: false; readonly reason: string } {
  const audience = resolveMcpOAuthAudience(server)
  if (audience) return { ok: true }
  for (const [key, value] of Object.entries(args)) {
    if (TOKENISH_KEYS.has(key) && !isBlank(value)) {
      return {
        ok: false,
        reason: `remote MCP server "${server.id}" has no oauthAudience binding; refusing token arg "${key}" (no token passthrough)`,
      }
    }
  }
  return { ok: true }
}

function isBlank(value: unknown): boolean {
  if (value === null || value === undefined) return true
  if (typeof value === "string") return value.trim().length === 0
  return false
}

/**
 * P3-3: Child (delegated) Runs get no MCP by default. A run is treated as a
 * child/no-MCP subject unless it runs as the owner. Grants must be delegable to
 * carry MCP into a child; default is fail-closed.
 */
export function mcpAllowedForRunSubject(
  subject: string,
  ownerSubject: string,
): boolean {
  return subject.trim() === ownerSubject.trim()
}
