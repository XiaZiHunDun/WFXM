import { dirname, isAbsolute, resolve } from "node:path"

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
  /** P3: server default risk class when tool entry omits risk. */
  readonly defaultRisk?: "low" | "medium" | "high"
  /** P3: default sandbox profile for Grant / audit skeleton. */
  readonly defaultSandboxProfile?: string
  /** P3: audit verbosity for MCP execution trace. */
  readonly auditPolicy?: "full" | "summary"
  /** P3-3: expected remote OAuth audience the host presents (no token passthrough without it). */
  readonly oauthAudience?: string
  readonly tools?: readonly McpManifestTool[]
}

export type McpManifest = {
  readonly version: number
  readonly servers: readonly McpManifestServer[]
}

/**
 * Resolve manifest-relative stdio args (e.g. `--openapi-spec` paths) against
 * the manifest file directory so repo-local specs work without ~/.butler.
 */
export function resolveManifestStdioArgs(
  manifestPath: string,
  args: readonly string[],
): readonly string[] {
  if (args.length === 0) return args
  const baseDir = dirname(resolve(manifestPath))
  const out: string[] = []
  for (let i = 0; i < args.length; i++) {
    const arg = args[i]
    if (arg === undefined) continue
    if (arg === "--openapi-spec") {
      const specPath = args[i + 1]
      if (specPath !== undefined) {
        out.push(arg)
        out.push(isAbsolute(specPath) ? specPath : resolve(baseDir, specPath))
        i++
        continue
      }
    }
    out.push(arg)
  }
  return out
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
    const defaultRisk = s["defaultRisk"]
    const defaultSandboxProfile = s["defaultSandboxProfile"]
    const auditPolicy = s["auditPolicy"]
    parsedServers.push({
      id: id.trim(),
      transport,
      ...(typeof s["url"] === "string" ? { url: s["url"] } : {}),
      ...(typeof s["command"] === "string" ? { command: s["command"] } : {}),
      ...(typeof s["oauthAudience"] === "string" && s["oauthAudience"].trim()
        ? { oauthAudience: s["oauthAudience"].trim() }
        : {}),
      ...(defaultRisk === "low" || defaultRisk === "medium" || defaultRisk === "high"
        ? { defaultRisk }
        : {}),
      ...(typeof defaultSandboxProfile === "string" && defaultSandboxProfile.trim()
        ? { defaultSandboxProfile: defaultSandboxProfile.trim() }
        : {}),
      ...(auditPolicy === "full" || auditPolicy === "summary" ? { auditPolicy } : {}),
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

/** Names whose invocation would grant a stdin/ipc shell — refused for stdio MCP. */
const SHELL_COMMANDS = new Set(["sh", "bash", "zsh", "fish", "/bin/sh", "/bin/bash", "/usr/bin/bash"])

export type McpPreScanResult =
  | { readonly ok: true }
  | { readonly ok: false; readonly reason: string }

/** Shell-wrap to inspect a stdio command name without invoking it (no token/[]). */
function commandName(server: { readonly command?: string }): string {
  const cmd = (server.command ?? "").trim()
  if (!cmd) return ""
  // strip quotes but not spaces so `npm exec` keeps its argv-0 semantics
  return cmd.replace(/^["']|["']$/g, "").split(/[ \t]+/)[0] ?? ""
}

/**
 * P3-3 pre-install scan: refuse servers whose config would create an
 * uncontrolled boundary. No network/exec — structural checks only.
 */
export function preScanMcpServer(server: McpManifestServer): McpPreScanResult {
  const cmd = (server.command ?? "").trim()
  const url = (server.url ?? "").trim()

  if (server.transport === "stdio") {
    const name = commandName(server)
    if (!name) {
      return { ok: false, reason: `stdio server "${server.id}" declares no command` }
    }
    if (SHELL_COMMANDS.has(name)) {
      return {
        ok: false,
        reason: `stdio server "${server.id}" would launch a shell ("${name}"); only specific interpreters are allowed`,
      }
    }
    if (cmd.includes("&&") || cmd.includes(";") || cmd.includes("|")) {
      return {
        ok: false,
        reason: `stdio server "${server.id}" contains shell meta-characters; single argv0 required`,
      }
    }
  }

  if (server.transport === "http" || server.transport === "sse") {
    if (!url) {
      return { ok: false, reason: `remote server "${server.id}" has no url` }
    }
    let parsed: URL
    try {
      parsed = new URL(url)
    } catch {
      return { ok: false, reason: `server "${server.id}" url is not a valid URL` }
    }
    const host = parsed.hostname.toLowerCase()
    if (parsed.protocol !== "https:" && host !== "localhost" && host !== "127.0.0.1" && host !== "::1") {
      return {
        ok: false,
        reason: `remote server "${server.id}" must use https (got ${parsed.protocol}//${host})`,
      }
    }
    if (server.command) {
      return {
        ok: false,
        reason: `server "${server.id}" declares both url and command; transport is ambiguous`,
      }
    }
  }

  return { ok: true }
}

export function preScanMcpManifest(manifest: McpManifest): McpPreScanResult {
  for (const server of manifest.servers) {
    const single = preScanMcpServer(server)
    if (!single.ok) return single
  }
  return { ok: true }
}
