import { isMcpCapability, MCP_CAPABILITY_PREFIX } from "@butler/domain/governance/types.js"

export { MCP_CAPABILITY_PREFIX, isMcpCapability }

/** True when `BUTLER_V5_MCP_ENABLED=1` (opt-in; default off). */
export function isMcpEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return (env["BUTLER_V5_MCP_ENABLED"] ?? "").trim() === "1"
}

/** Comma-separated stub tool names for scaffold/testing without a live MCP server. */
export function mcpStubToolNames(env: NodeJS.ProcessEnv = process.env): readonly string[] {
  const raw = (env["BUTLER_V5_MCP_TOOL_NAMES"] ?? "").trim()
  if (!raw) return []
  return raw
    .split(/[,\s]+/)
    .map((part) => part.trim())
    .filter((part) => part.length > 0)
}

export function toMcpCapabilityName(serverToolName: string): string {
  const trimmed = serverToolName.trim()
  if (!trimmed) throw new Error("MCP tool name is required")
  if (trimmed.startsWith(MCP_CAPABILITY_PREFIX)) return trimmed
  return `${MCP_CAPABILITY_PREFIX}${trimmed}`
}
