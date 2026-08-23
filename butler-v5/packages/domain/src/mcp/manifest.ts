export type McpManifestTool = {
  readonly name: string
  readonly description?: string
  readonly risk?: "low" | "medium" | "high"
}

export type McpManifestServer = {
  readonly id: string
  readonly transport: "http" | "sse" | "stdio"
  readonly url?: string
  readonly command?: string
  readonly args?: readonly string[]
  readonly tools?: readonly McpManifestTool[]
}

export type McpManifest = {
  readonly version: number
  readonly servers: readonly McpManifestServer[]
}

export function parseMcpManifest(raw: unknown): { readonly ok: true; readonly value: McpManifest } | { readonly ok: false; readonly reason: string } {
  if (!raw || typeof raw !== "object") {
    return { ok: false, reason: "manifest must be an object" }
  }
  const rec = raw as Record<string, unknown>
  const version = rec["version"]
  const servers = rec["servers"]
  if (typeof version !== "number" || !Number.isFinite(version)) {
    return { ok: false, reason: "manifest.version must be a number" }
  }
  if (!Array.isArray(servers)) {
    return { ok: false, reason: "manifest.servers must be an array" }
  }
  const parsedServers: McpManifestServer[] = []
  for (const entry of servers) {
    if (!entry || typeof entry !== "object") {
      return { ok: false, reason: "manifest.servers entries must be objects" }
    }
    const s = entry as Record<string, unknown>
    const id = s["id"]
    const transport = s["transport"]
    if (typeof id !== "string" || !id.trim()) {
      return { ok: false, reason: "manifest server id is required" }
    }
    if (transport !== "http" && transport !== "sse" && transport !== "stdio") {
      return { ok: false, reason: `invalid transport for server ${id}` }
    }
    parsedServers.push({
      id: id.trim(),
      transport,
      ...(typeof s["url"] === "string" ? { url: s["url"] } : {}),
      ...(typeof s["command"] === "string" ? { command: s["command"] } : {}),
      ...(Array.isArray(s["args"])
        ? {
            args: s["args"]
              .filter((part) => typeof part === "string" && part.trim().length > 0)
              .map((part) => (part as string).trim()),
          }
        : {}),
      ...(Array.isArray(s["tools"])
        ? {
            tools: s["tools"]
              .filter((t) => t && typeof t === "object" && typeof (t as { name?: string }).name === "string")
              .map((t) => {
                const tool = t as { name: string; description?: string; risk?: string }
                return {
                  name: tool.name,
                  ...(tool.description ? { description: tool.description } : {}),
                  ...(tool.risk === "low" || tool.risk === "medium" || tool.risk === "high"
                    ? { risk: tool.risk }
                    : {}),
                }
              }),
          }
        : {}),
    })
  }
  return { ok: true, value: { version, servers: parsedServers } }
}

export function mcpServerIds(manifest: McpManifest): readonly string[] {
  return manifest.servers.map((s) => s.id)
}

export function findMcpServer(
  manifest: McpManifest,
  serverId: string,
): McpManifestServer | undefined {
  const id = serverId.trim()
  return manifest.servers.find((server) => server.id === id)
}
