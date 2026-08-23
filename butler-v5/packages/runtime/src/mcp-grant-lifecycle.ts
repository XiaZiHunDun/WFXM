import type { RuntimeStore } from "@butler/domain/runtime.js"
import { normalizeMcpServerId } from "@butler/domain/governance/mcp-tool-capability.js"

/** Revoke active MCP ScopedGrants for a server (fail-closed on uninstall / consent removal). */
export async function revokeScopedGrantsForMcpServer(
  store: RuntimeStore,
  serverId: string,
  now: Date = new Date(),
): Promise<number> {
  return store.revokeScopedGrantsForMcpServer(normalizeMcpServerId(serverId), now)
}
