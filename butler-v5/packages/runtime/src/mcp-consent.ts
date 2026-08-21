import { parseMcpManifest, type McpManifest } from "@butler/domain/mcp/manifest.js"

function envTruthy(raw: string | undefined): boolean {
  if (!raw) return false
  const text = raw.trim().toLowerCase()
  return text === "1" || text === "true" || text === "yes" || text === "on"
}

export function mcpRequireConsent(env: NodeJS.ProcessEnv = process.env): boolean {
  return envTruthy(env["BUTLER_V5_MCP_REQUIRE_CONSENT"])
}

export function parseMcpConsentServers(env: NodeJS.ProcessEnv = process.env): ReadonlySet<string> {
  const raw = (env["BUTLER_V5_MCP_CONSENT"] ?? "").trim()
  if (!raw) return new Set()
  return new Set(
    raw
      .split(/[,\s]+/)
      .map((part) => part.trim())
      .filter((part) => part.length > 0),
  )
}

export function mcpServerIdFromEnv(env: NodeJS.ProcessEnv = process.env): string {
  const explicit = (env["BUTLER_V5_MCP_SERVER_ID"] ?? "").trim()
  if (explicit) return explicit
  const url = (env["BUTLER_V5_MCP_URL"] ?? "").trim()
  if (url) {
    try {
      return new URL(url).hostname.toLowerCase()
    } catch {
      return "mcp-http"
    }
  }
  const command = (env["BUTLER_V5_MCP_COMMAND"] ?? "").trim()
  if (command) return command.split(/[/\\]/).pop() ?? "mcp-stdio"
  return "mcp-default"
}

export function isMcpServerConsented(
  serverId: string,
  env: NodeJS.ProcessEnv = process.env,
): boolean {
  if (!mcpRequireConsent(env)) return true
  const allowed = parseMcpConsentServers(env)
  return allowed.has(serverId.trim())
}

export function assertMcpServerConsented(
  serverId: string,
  env: NodeJS.ProcessEnv = process.env,
): { readonly ok: true } | { readonly ok: false; readonly reason: string } {
  if (isMcpServerConsented(serverId, env)) return { ok: true }
  return {
    ok: false,
    reason: `MCP server "${serverId}" is not in BUTLER_V5_MCP_CONSENT (BUTLER_V5_MCP_REQUIRE_CONSENT=1)`,
  }
}

export function loadMcpManifestFromJson(
  raw: string,
): { readonly ok: true; readonly manifest: McpManifest } | { readonly ok: false; readonly reason: string } {
  let parsed: unknown
  try {
    parsed = JSON.parse(raw) as unknown
  } catch {
    return { ok: false, reason: "MCP manifest is not valid JSON" }
  }
  const manifest = parseMcpManifest(parsed)
  if (!manifest.ok) return { ok: false, reason: manifest.reason }
  return { ok: true, manifest: manifest.value }
}

export function manifestAllowsServer(manifest: McpManifest, serverId: string): boolean {
  return manifest.servers.some((server) => server.id === serverId.trim())
}
