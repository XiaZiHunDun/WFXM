import type { ILinkResult } from "@butler/adapters"
import { isMcpEnabled, mcpStubToolNames } from "@butler/runtime/mcp-gate.js"

function envTruthy(raw: string | undefined): boolean {
  if (!raw) return false
  const text = raw.trim().toLowerCase()
  return text === "1" || text === "true" || text === "yes" || text === "on"
}

export type McpServerConfig = {
  readonly url: string
  readonly timeoutMs: number
  readonly token?: string
}

export function parseMcpServerConfig(env: NodeJS.ProcessEnv): ILinkResult<McpServerConfig> {
  if (!isMcpEnabled(env)) {
    return { ok: false, reason: "BUTLER_V5_MCP_ENABLED is off" }
  }
  const url = (env["BUTLER_V5_MCP_URL"] ?? "").trim()
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
  const timeoutMs = Number(env["BUTLER_V5_MCP_TIMEOUT_MS"] ?? 30_000)
  const token = (env["BUTLER_V5_MCP_TOKEN"] ?? "").trim()
  return {
    ok: true,
    value: {
      url,
      timeoutMs: Number.isFinite(timeoutMs) && timeoutMs > 0 ? timeoutMs : 30_000,
      ...(token ? { token } : {}),
    },
  }
}

export function mcpUsesStubTools(env: NodeJS.ProcessEnv): boolean {
  return isMcpEnabled(env) && mcpStubToolNames(env).length > 0 && !(env["BUTLER_V5_MCP_URL"] ?? "").trim()
}

export function mcpFailClosedOnBootstrap(env: NodeJS.ProcessEnv): boolean {
  return envTruthy(env["BUTLER_V5_MCP_REQUIRED"])
}
