import type { ILinkResult } from "@butler/adapters"
import type { McpManifestServer } from "@butler/domain/mcp/manifest.js"
import { isMcpEnabled, mcpStubToolNames } from "@butler/runtime/mcp-gate.js"

function envTruthy(raw: string | undefined): boolean {
  if (!raw) return false
  const text = raw.trim().toLowerCase()
  return text === "1" || text === "true" || text === "yes" || text === "on"
}

export type McpTransportKind = "http" | "stdio" | "sse"

export type McpHttpConnection = {
  readonly kind: "http"
  readonly url: string
  readonly timeoutMs: number
  readonly token?: string
}

export type McpSseConnection = {
  readonly kind: "sse"
  readonly url: string
  readonly timeoutMs: number
  readonly token?: string
}

export type McpStdioConnection = {
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
  const timeoutMs = Number(env["BUTLER_V5_MCP_TIMEOUT_MS"] ?? 30_000)
  return Number.isFinite(timeoutMs) && timeoutMs > 0 ? timeoutMs : 30_000
}

export function parseMcpStdioArgs(env: NodeJS.ProcessEnv): readonly string[] {
  const raw = (env["BUTLER_V5_MCP_ARGS"] ?? "").trim()
  if (!raw) return []
  return raw.split(/[,\s]+/).filter((part) => part.length > 0)
}

function resolveMcpUrl(
  env: NodeJS.ProcessEnv,
  manifestServer?: McpManifestServer | null,
): string {
  return (env["BUTLER_V5_MCP_URL"] ?? "").trim() || (manifestServer?.url ?? "").trim()
}

function resolveMcpCommand(
  env: NodeJS.ProcessEnv,
  manifestServer?: McpManifestServer | null,
): string {
  return (env["BUTLER_V5_MCP_COMMAND"] ?? "").trim() || (manifestServer?.command ?? "").trim()
}

export function parseMcpConnectionConfig(
  env: NodeJS.ProcessEnv,
  manifestServer?: McpManifestServer | null,
): ILinkResult<McpConnectionConfig> {
  if (!isMcpEnabled(env)) {
    return { ok: false, reason: "BUTLER_V5_MCP_ENABLED is off" }
  }
  const kind = parseMcpTransportKind(env, manifestServer)
  const timeoutMs = parseTimeoutMs(env)
  const token = (env["BUTLER_V5_MCP_TOKEN"] ?? "").trim()

  if (kind === "stdio") {
    const command = resolveMcpCommand(env, manifestServer)
    if (!command) {
      return { ok: false, reason: "BUTLER_V5_MCP_COMMAND is required for stdio transport" }
    }
    return {
      ok: true,
      value: {
        kind: "stdio",
        command,
        args: parseMcpStdioArgs(env),
        timeoutMs,
      },
    }
  }

  const url = resolveMcpUrl(env, manifestServer)
  if (!url) {
    return { ok: false, reason: "BUTLER_V5_MCP_URL is not set" }
  }
  try {
    const parsed = new URL(url)
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return { ok: false, reason: "BUTLER_V5_MCP_URL must be http(s)" }
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

/** @deprecated use parseMcpConnectionConfig */
export type McpServerConfig = McpHttpConnection

/** @deprecated use parseMcpConnectionConfig */
export function parseMcpServerConfig(env: NodeJS.ProcessEnv): ILinkResult<McpHttpConnection> {
  const parsed = parseMcpConnectionConfig(env)
  if (!parsed.ok) return parsed
  if (parsed.value.kind !== "http") {
    return { ok: false, reason: "BUTLER_V5_MCP_TRANSPORT is not http" }
  }
  return parsed
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
