export {
  MCP_CAPABILITY_PREFIX,
  isMcpCapability,
  toMcpCapabilityName,
  toMcpCapabilityNameForServer,
} from "@butler/domain/governance/mcp-tool-capability.js"

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
