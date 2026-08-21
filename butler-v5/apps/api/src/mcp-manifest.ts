import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import type { McpManifest, McpManifestServer } from "@butler/domain/mcp/manifest.js"
import { findMcpServer } from "@butler/domain/mcp/manifest.js"
import {
  loadMcpManifestFromJson,
  manifestAllowsServer,
} from "@butler/runtime/mcp-consent.js"

export type McpManifestLoadResult =
  | { readonly kind: "none" }
  | { readonly kind: "loaded"; readonly manifest: McpManifest }
  | { readonly kind: "error"; readonly reason: string }

export function mcpManifestPathFromEnv(env: NodeJS.ProcessEnv = process.env): string | null {
  const raw = (env["BUTLER_V5_MCP_MANIFEST_PATH"] ?? "").trim()
  return raw || null
}

export function loadMcpManifestFromPath(path: string): McpManifestLoadResult {
  try {
    const abs = resolve(path)
    const raw = readFileSync(abs, "utf8")
    const parsed = loadMcpManifestFromJson(raw)
    if (!parsed.ok) {
      return { kind: "error", reason: parsed.reason }
    }
    return { kind: "loaded", manifest: parsed.manifest }
  } catch (err) {
    return {
      kind: "error",
      reason: err instanceof Error ? err.message : String(err),
    }
  }
}

export function loadMcpManifestFromEnv(env: NodeJS.ProcessEnv = process.env): McpManifestLoadResult {
  const path = mcpManifestPathFromEnv(env)
  if (!path) return { kind: "none" }
  return loadMcpManifestFromPath(path)
}

export function assertMcpServerInManifest(
  manifest: McpManifest,
  serverId: string,
): { readonly ok: true } | { readonly ok: false; readonly reason: string } {
  if (manifestAllowsServer(manifest, serverId)) return { ok: true }
  return {
    ok: false,
    reason: `MCP server "${serverId}" is not declared in BUTLER_V5_MCP_MANIFEST_PATH`,
  }
}

export function resolveMcpManifestServer(
  manifest: McpManifest,
  serverId: string,
): McpManifestServer | null {
  return findMcpServer(manifest, serverId) ?? null
}
