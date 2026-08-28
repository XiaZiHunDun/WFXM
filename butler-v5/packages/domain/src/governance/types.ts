export type RiskLevel = "low" | "medium" | "high"

export type ActionKind = "read" | "write" | "command" | "delegate" | "outbound" | "model"

import {
  grantScopeMatchesMcpTool,
  isMcpCapability,
  normalizeMcpGrantScope,
  parseMcpCapability,
  type McpGrantScope,
} from "./mcp-tool-capability.js"

export {
  MCP_CAPABILITY_PREFIX,
  isMcpCapability,
  type McpGrantScope,
} from "./mcp-tool-capability.js"

export interface ActionRequest {
  readonly kind: ActionKind
  readonly capability: string
  readonly subject: string
  readonly resource: string
  readonly risk: RiskLevel
  readonly digest: string
  readonly payload: Readonly<Record<string, unknown>>
}

export type PolicyDecision =
  | { readonly _tag: "Allow" }
  | { readonly _tag: "Deny"; readonly reason: string }
  | {
      readonly _tag: "Ask"
      readonly question: string
      readonly expiresAtMs: number
    }

export interface ScopedGrantScope {
  readonly paths?: readonly string[]
  readonly network?: "deny" | "allow"
  /** When set with network allow, outbound fetches must target one of these hostnames. */
  readonly networkHosts?: readonly string[]
  readonly maxUses?: number
  /** When set, only the exact action digest from approval may execute. */
  readonly digest?: string
  /** P3: bind MCP Grant to a specific server + tool name. */
  readonly mcp?: McpGrantScope
}

export interface ScopedGrantRecord {
  readonly id: string
  readonly runId: string
  readonly subject: string
  /**
   * D2.2 first-class column mirror (DESIGN §10.3 minimum field). Source of truth for
   * capability matching (grantMatchesAction + findActiveGrant SQL + revoke filter).
   * Pre-migration rows fall back to scope.capabilities[0] during hydrate.
   */
  readonly capability: string
  readonly scope: ScopedGrantScope
  readonly remainingUses: number | null
  readonly expiresAtMs: number
  readonly createdAtMs: number
  /** Child Run may receive a narrowed copy only when true. Default false. */
  readonly delegable: boolean
  /** Waiting approval Step id that issued this grant; null for preconfigured grants. */
  readonly approvalId: string | null
  /** Elevated sandbox profile when Grant lifts provider default isolation. */
  readonly sandboxProfile: string | null
  /** host:port list for workspace-write-network-allowlist (P2b). */
  readonly networkAllowlist: readonly string[] | null
}

export interface PermissionPolicy {
  readonly ownerSubject: string
  readonly alwaysConfirm: readonly string[]
  readonly denyByDefault: readonly ActionKind[]
  /** When true, owner low-risk MCP tools skip per-call Ask (BUTLER_V5_MCP_READONLY_AUTO_ALLOW). */
  readonly mcpReadonlyAutoAllow?: boolean
}

export function decidePolicy(
  request: ActionRequest,
  policy: PermissionPolicy,
  nowMs: number,
  grant: ScopedGrantRecord | null,
): PolicyDecision {
  const mcpNeedsConfirm =
    isMcpCapability(request.capability) &&
    !(
      policy.mcpReadonlyAutoAllow === true &&
      request.risk === "low" &&
      request.subject === policy.ownerSubject
    )
  const needsConfirm = policy.alwaysConfirm.includes(request.capability) || mcpNeedsConfirm

  if (needsConfirm) {
    if (
      grant &&
      grant.expiresAtMs > nowMs &&
      grantMatchesAction(grant, request) &&
      (grant.remainingUses === null || grant.remainingUses > 0)
    ) {
      return { _tag: "Allow" }
    }
    return {
      _tag: "Ask",
      question: `Confirm ${request.capability} on ${request.resource}?`,
      expiresAtMs: nowMs + 15 * 60_000,
    }
  }

  if (policy.denyByDefault.includes(request.kind) && request.risk === "high") {
    if (!grant || grant.expiresAtMs <= nowMs) {
      return { _tag: "Deny", reason: "high-risk action without active grant" }
    }
    if (!grantMatchesAction(grant, request)) {
      return { _tag: "Deny", reason: "grant scope mismatch" }
    }
    if (grant.remainingUses !== null && grant.remainingUses <= 0) {
      return { _tag: "Deny", reason: "grant exhausted" }
    }
  }

  if (request.risk === "high" && request.subject !== policy.ownerSubject) {
    return { _tag: "Deny", reason: "high-risk action from non-owner subject" }
  }

  return { _tag: "Allow" }
}

export function consumeGrantUse(grant: ScopedGrantRecord): ScopedGrantRecord {
  if (grant.remainingUses === null) return grant
  return { ...grant, remainingUses: Math.max(0, grant.remainingUses - 1) }
}

export function normalizeGrantPath(path: string): string {
  return path.trim().replace(/\\/g, "/")
}

export function normalizeGrantHost(host: string): string {
  return host.trim().toLowerCase()
}

export function actionRequiresNetworkGrant(kind: ActionKind, capability: string): boolean {
  if (kind === "outbound") return true
  if (isMcpCapability(capability)) return true
  return false
}

export function buildScopedGrantScopeFromPending(input: {
  readonly capability: string
  readonly resource: string
  readonly digest: string
  readonly networkHosts?: readonly string[]
  /** When true, stamp network allow (e.g. Grant networkAllowlist on run_command). */
  readonly forceNetworkAllow?: boolean
  /** P3: MCP server id for per-tool ScopedGrant scope. */
  readonly mcpServerId?: string
}): ScopedGrantScope {
  let scope: ScopedGrantScope = {
    digest: input.digest,
  }
  if (
    input.capability === "send_wechat_file" ||
    input.capability === "read_file" ||
    input.capability === "write_file"
  ) {
    const path = input.resource.trim()
    if (path) {
      scope = { ...scope, paths: [normalizeGrantPath(path)] }
    }
  }
  const needsNetwork =
    input.forceNetworkAllow === true ||
    actionRequiresNetworkGrant(outboundKindForCapability(input.capability), input.capability)
  if (needsNetwork) {
    scope = {
      ...scope,
      network: "allow",
      ...(input.networkHosts && input.networkHosts.length > 0
        ? { networkHosts: input.networkHosts.map(normalizeGrantHost) }
        : {}),
    }
  }
  if (isMcpCapability(input.capability) && input.mcpServerId?.trim()) {
    const parsed = parseMcpCapability(input.capability, [input.mcpServerId])
    const mcpScope =
      parsed &&
      normalizeMcpGrantScope({
        serverId: input.mcpServerId,
        toolName: parsed.toolName,
      })
    if (mcpScope) {
      scope = {
        ...scope,
        mcp: mcpScope,
      }
    }
  }
  return scope
}

function outboundKindForCapability(capability: string): ActionKind {
  if (capability === "send_wechat_file") return "outbound"
  if (isMcpCapability(capability)) return "command"
  return "read"
}

export function grantAllowsNetworkHost(
  grant: ScopedGrantRecord,
  hostname: string,
): boolean {
  if (grant.scope.network !== "allow") return false
  const hosts = grant.scope.networkHosts
  if (!hosts || hosts.length === 0) return true
  const normalized = normalizeGrantHost(hostname)
  return hosts.some((host) => normalizeGrantHost(host) === normalized)
}

export function grantMatchesAction(grant: ScopedGrantRecord, request: ActionRequest): boolean {
  if (grant.capability !== request.capability) {
    return false
  }
  if (isMcpCapability(request.capability)) {
    const serverIds = grant.scope.mcp ? [grant.scope.mcp.serverId] : []
    const parsed = parseMcpCapability(request.capability, serverIds)
    if (!parsed || !grantScopeMatchesMcpTool(grant.scope, parsed)) {
      return false
    }
  }
  if (grant.scope.digest && grant.scope.digest !== request.digest) {
    return false
  }
  if (grant.scope.paths && grant.scope.paths.length > 0) {
    const resource = normalizeGrantPath(request.resource)
    const allowed = grant.scope.paths.some((path) => normalizeGrantPath(path) === resource)
    if (!allowed) {
      return false
    }
  }
  if (actionRequiresNetworkGrant(request.kind, request.capability)) {
    if (grant.scope.network !== "allow") {
      return false
    }
  }
  return true
}
