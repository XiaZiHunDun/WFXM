import type { ILinkResult } from "@butler/adapters"
import { envTruthy, parseMcpTimeoutMs } from "./env-util.js"
import type { McpManifestServer } from "@butler/domain/mcp/manifest.js"
import { resolveManifestStdioArgs } from "@butler/ports/mcp-manifest-path.js"
import { isMcpEnabled, mcpStubToolNames } from "@butler/runtime/mcp-gate.js"


export type McpTransportKind = "http" | "stdio" | "sse"

type McpHttpConnection = {
  readonly kind: "http"
  readonly url: string
  readonly timeoutMs: number
  readonly token?: string
}

type McpSseConnection = {
  readonly kind: "sse"
  readonly url: string
  readonly timeoutMs: number
  readonly token?: string
}

type McpStdioConnection = {
  readonly kind: "stdio"
  readonly command: string
  readonly args: readonly string[]
  readonly timeoutMs: number
  readonly env?: Readonly<Record<string, string>>
}

export type McpConnectionConfig = McpHttpConnection | McpSseConnection | McpStdioConnection

function envTransportKind(env: NodeJS.ProcessEnv): McpTransportKind | null {
  const raw = (env["BUTLER_V5_MCP_TRANSPORT"] ?? "").trim().toLowerCase()
  if (raw === "stdio" || raw === "sse" || raw === "http") return raw
  return null
}

export function parseMcpTransportKind(
  env: NodeJS.ProcessEnv,
  manifestServer?: McpManifestServer | null,
): McpTransportKind {
  return envTransportKind(env) ?? manifestServer?.transport ?? "http"
}

function parseTimeoutMs(env: NodeJS.ProcessEnv): number {
  // D72 T4 (audit #18 CQ-017): call shared helper instead of inlined
  // Number() / Number.isFinite() dance.
  return parseMcpTimeoutMs(env)
}

function parseMcpStdioArgs(
  env: NodeJS.ProcessEnv,
  manifestServer?: McpManifestServer | null,
  serverId?: string,
): readonly string[] {
  if (manifestServer?.args && manifestServer.args.length > 0 && preferManifestConnection(env, serverId)) {
    return manifestServer.args
  }
  const envArgs = parseMcpStdioArgsFromEnv(env)
  if (envArgs.length > 0) {
    return envArgs
  }
  return manifestServer?.args ?? []
}

function parseMcpStdioArgsFromEnv(env: NodeJS.ProcessEnv): readonly string[] {
  const raw = (env["BUTLER_V5_MCP_ARGS"] ?? "").trim()
  if (!raw) return []
  return raw.split(/[,\s]+/).filter((part) => part.length > 0)
}

function useEnvConnectionOverrides(env: NodeJS.ProcessEnv, serverId?: string): boolean {
  const explicit = (env["BUTLER_V5_MCP_SERVER_ID"] ?? "").trim()
  const manifestPath = (env["BUTLER_V5_MCP_MANIFEST_PATH"] ?? "").trim()
  if (!manifestPath) {
    return true
  }
  if (!explicit) {
    return false
  }
  if (!serverId) {
    return true
  }
  return explicit === serverId
}

function scopedEnvForServer(env: NodeJS.ProcessEnv, serverId?: string): NodeJS.ProcessEnv {
  if (useEnvConnectionOverrides(env, serverId)) {
    return env
  }
  return {
    ...env,
    BUTLER_V5_MCP_COMMAND: "",
    BUTLER_V5_MCP_ARGS: "",
    BUTLER_V5_MCP_URL: "",
    BUTLER_V5_MCP_TRANSPORT: "",
  }
}

function resolveMcpUrl(
  env: NodeJS.ProcessEnv,
  manifestServer?: McpManifestServer | null,
  serverId?: string,
): string {
  if (manifestServer?.url && preferManifestConnection(env, serverId)) {
    return manifestServer.url.trim()
  }
  return (env["BUTLER_V5_MCP_URL"] ?? "").trim() || (manifestServer?.url ?? "").trim()
}

function resolveMcpCommand(
  env: NodeJS.ProcessEnv,
  manifestServer?: McpManifestServer | null,
  serverId?: string,
): string {
  if (manifestServer?.command && preferManifestConnection(env, serverId)) {
    return manifestServer.command.trim()
  }
  return (env["BUTLER_V5_MCP_COMMAND"] ?? "").trim() || (manifestServer?.command ?? "").trim()
}

function preferManifestConnection(env: NodeJS.ProcessEnv, serverId?: string): boolean {
  const manifestPath = (env["BUTLER_V5_MCP_MANIFEST_PATH"] ?? "").trim()
  if (!manifestPath) {
    return false
  }
  const explicit = (env["BUTLER_V5_MCP_SERVER_ID"] ?? "").trim()
  if (!explicit) {
    return true
  }
  return !serverId || explicit === serverId
}

export function parseMcpConnectionConfig(
  env: NodeJS.ProcessEnv,
  manifestServer?: McpManifestServer | null,
  options: { readonly serverId?: string } = {},
): ILinkResult<McpConnectionConfig> {
  if (!isMcpEnabled(env)) {
    return { ok: false, reason: "BUTLER_V5_MCP_ENABLED is off" }
  }
  const scopedEnv = scopedEnvForServer(env, options.serverId)
  const kind = parseMcpTransportKind(scopedEnv, manifestServer)
  const timeoutMs = parseTimeoutMs(env)
  const token = (env["BUTLER_V5_MCP_TOKEN"] ?? "").trim()

  if (kind === "stdio") {
    const command = resolveMcpCommand(scopedEnv, manifestServer, options.serverId)
    if (!command) {
      return { ok: false, reason: "BUTLER_V5_MCP_COMMAND is required for stdio transport" }
    }
    let args = parseMcpStdioArgs(scopedEnv, manifestServer, options.serverId)
    const manifestPath = (env["BUTLER_V5_MCP_MANIFEST_PATH"] ?? "").trim()
    if (manifestPath && args.length > 0) {
      args = resolveManifestStdioArgs(manifestPath, args)
    }
    return {
      ok: true,
      value: {
        kind: "stdio",
        command,
        args,
        timeoutMs,
      },
    }
  }

  const url = resolveMcpUrl(scopedEnv, manifestServer, options.serverId)
  if (!url) {
    return { ok: false, reason: "BUTLER_V5_MCP_URL is not set" }
  }
  try {
    const parsed = new URL(url)
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return { ok: false, reason: "BUTLER_V5_MCP_URL must be http(s)" }
    }
    // D71 T2 (audit #12 CQ-012 + SEC-001): refuse hosts that resolve to
    // private/loopback/link-local/metadata ranges. MCP server URLs are
    // operator-configured but a typo (e.g. 10.0.0.1) or hostile manifest
    // would otherwise let the HTTP/SSE transport probe internal services
    // from inside the butler process. The escape hatch is an explicit
    // env opt-in (BUTLER_V5_MCP_ALLOW_PRIVATE_HOSTS=1) for dev/test
    // setups that intentionally point at 127.0.0.1.
    if (!envAllowsPrivateMcpHosts(scopedEnv) && isBlockedMcpHost(parsed.hostname)) {
      return {
        ok: false,
        reason: `MCP host ${parsed.hostname} is in a private/loopback/link-local/metadata range; set BUTLER_V5_MCP_ALLOW_PRIVATE_HOSTS=1 to override (dev/test only)`,
      }
    }
  } catch {
    return { ok: false, reason: "BUTLER_V5_MCP_URL is not a valid URL" }
  }

  if (kind === "sse") {
    return {
      ok: true,
      value: {
        kind: "sse",
        url,
        timeoutMs,
        ...(token ? { token } : {}),
      },
    }
  }

  return {
    ok: true,
    value: {
      kind: "http",
      url,
      timeoutMs,
      ...(token ? { token } : {}),
    },
  }
}

export function mcpHasServerEndpoint(
  env: NodeJS.ProcessEnv,
  manifestServer?: McpManifestServer | null,
): boolean {
  if (resolveMcpUrl(env, manifestServer)) return true
  if (resolveMcpCommand(env, manifestServer)) return true
  return false
}

export function mcpUsesStubTools(
  env: NodeJS.ProcessEnv,
  manifestServer?: McpManifestServer | null,
): boolean {
  return (
    isMcpEnabled(env) &&
    mcpStubToolNames(env).length > 0 &&
    !mcpHasServerEndpoint(env, manifestServer)
  )
}

export function mcpFailClosedOnBootstrap(env: NodeJS.ProcessEnv): boolean {
  return envTruthy(env["BUTLER_V5_MCP_REQUIRED"])
}

/**
 * D71 T2 (audit #12 CQ-012 / SEC-001): host allowlist for MCP HTTP/SSE
 * transports. Rejects private/loopback/link-local/metadata ranges by
 * literal hostname match — operator misconfiguration or hostile manifest
 * would otherwise let the transport probe internal services from inside
 * the butler process. The allowlist is conservative; operator must set
 * BUTLER_V5_MCP_ALLOW_PRIVATE_HOSTS=1 to override (dev/test only).
 *
 * Closure of pre-scoped D70 #5 (MCP HTTP/SSE SSRF) and audit #12 D71
 * carry-forward. Mirrors the post-D63 fail-closed posture for owner
 * routes (loopback-only) and Telegram/Slack channels (signature + jwt).
 */
export function isBlockedMcpHost(hostname: string): boolean {
  const host = hostname.toLowerCase()
  // Loopback IPv4 + IPv6 (::1 already normalized by URL parser to [::1])
  if (host === "127.0.0.1" || host === "::1" || host === "localhost") return true
  // AWS / GCP / Azure metadata endpoint
  if (host === "169.254.169.254" || host === "metadata.google.internal") return true
  // Wildcard / unspecified
  if (host === "0.0.0.0" || host === "::") return true
  // RFC 1918 private IPv4 ranges — check literal strings to avoid
  // pulling in a dependency on `net` or `ipaddr.js`. CIDR-equality:
  if (host.startsWith("10.")) return true
  if (host.startsWith("192.168.")) return true
  if (host === "172.16." || host.startsWith("172.16.")) return true
  if (host === "172.17." || host.startsWith("172.17.")) return true
  // 172.16.0.0 — 172.31.255.255 covered by 172.1x / 172.2x / 172.3x
  if (host.startsWith("172.16.") || host.startsWith("172.17.") ||
      host.startsWith("172.18.") || host.startsWith("172.19.") ||
      host.startsWith("172.20.") || host.startsWith("172.21.") ||
      host.startsWith("172.22.") || host.startsWith("172.23.") ||
      host.startsWith("172.24.") || host.startsWith("172.25.") ||
      host.startsWith("172.26.") || host.startsWith("172.27.") ||
      host.startsWith("172.28.") || host.startsWith("172.29.") ||
      host.startsWith("172.30.") || host.startsWith("172.31.")) return true
  // Link-local IPv4
  if (host.startsWith("169.254.")) return true
  // IPv6 ULA fc00::/7 (covers fc00-fdff)
  if (host.startsWith("fc") || host.startsWith("fd")) {
    // very rough: assume 4-char hex prefix; full validation would parse
    // the address — sufficient for a host-string literal check.
    return true
  }
  // IPv6 link-local fe80::/10
  if (host.startsWith("fe80:") || host.startsWith("fe80::") || host.startsWith("[fe80")) return true
  return false
}

export function envAllowsPrivateMcpHosts(env: NodeJS.ProcessEnv): boolean {
  return envTruthy(env["BUTLER_V5_MCP_ALLOW_PRIVATE_HOSTS"])
}

/**
 * D72 T4 (audit #18 SEC-004): host allowlist for the iLink poller's
 * V5_INBOUND_URL target (the inbound webhook the poller pushes WeChat
 * events to). Mirrors `isBlockedMcpHost` but EXEMPTS loopback ranges —
 * the default V5_INBOUND_URL is `http://127.0.0.1:3000/v1/wechat/inbound`
 * which is the legitimate in-process loopback target. RFC 1918, link-local,
 * and metadata endpoints still get blocked.
 *
 * Operator can set BUTLER_V5_INBOUND_ALLOW_PRIVATE_HOSTS=1 to disable the
 * block entirely (dev/test only — production should never need this).
 *
 * Closure of pre-scoped D70 #4 (V5_INBOUND_URL SSRF).
 */
export function isBlockedInboundHost(hostname: string): boolean {
  const host = hostname.toLowerCase()
  // Loopback NOT blocked — default V5_INBOUND_URL points at 127.0.0.1
  // AWS / GCP / Azure metadata endpoint
  if (host === "169.254.169.254" || host === "metadata.google.internal") return true
  // Wildcard / unspecified
  if (host === "0.0.0.0" || host === "::") return true
  // RFC 1918 private IPv4 ranges — literal string checks (no `net` dep)
  if (host.startsWith("10.")) return true
  if (host.startsWith("192.168.")) return true
  // 172.16.0.0 — 172.31.255.255 covered by 172.1x / 172.2x / 172.3x
  if (host.startsWith("172.16.") || host.startsWith("172.17.") ||
      host.startsWith("172.18.") || host.startsWith("172.19.") ||
      host.startsWith("172.20.") || host.startsWith("172.21.") ||
      host.startsWith("172.22.") || host.startsWith("172.23.") ||
      host.startsWith("172.24.") || host.startsWith("172.25.") ||
      host.startsWith("172.26.") || host.startsWith("172.27.") ||
      host.startsWith("172.28.") || host.startsWith("172.29.") ||
      host.startsWith("172.30.") || host.startsWith("172.31.")) return true
  // Link-local IPv4
  if (host.startsWith("169.254.")) return true
  // IPv6 ULA fc00::/7
  if (host.startsWith("fc") || host.startsWith("fd")) return true
  // IPv6 link-local fe80::/10
  if (host.startsWith("fe80:") || host.startsWith("fe80::") || host.startsWith("[fe80")) return true
  return false
}

export function envAllowsPrivateInboundHosts(env: NodeJS.ProcessEnv): boolean {
  return envTruthy(env["BUTLER_V5_INBOUND_ALLOW_PRIVATE_HOSTS"])
}
