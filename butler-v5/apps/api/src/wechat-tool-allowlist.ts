/**
 * Opt-in WeChat Loop tool allowlist (core + per-project MCP subset).
 *
 * BUTLER_V5_WECHAT_TOOL_ALLOWLIST_PATH=config/wechat-tool-allowlist.json
 */
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import {
  buildWechatAllowedToolNames,
  type WechatToolAllowlistConfig,
} from "@butler/domain/runtime.js"
import type { McpToolBundle } from "./mcp-bootstrap.js"
import { isSubagentEnabled } from "./subagent-config.js"

function parseProjectEntry(raw: unknown): { readonly mcpTools: readonly string[] | "*" } | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null
  const obj = raw as Record<string, unknown>
  if (obj["mcpTools"] === "*") {
    return { mcpTools: "*" }
  }
  if (!Array.isArray(obj["mcpTools"])) {
    return { mcpTools: [] }
  }
  const mcpTools = obj["mcpTools"]
    .filter((part): part is string => typeof part === "string" && part.trim().length > 0)
    .map((part) => part.trim())
  return { mcpTools }
}

export function parseWechatToolAllowlistJson(text: string): WechatToolAllowlistConfig | null {
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    return null
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null
  const root = parsed as Record<string, unknown>
  const version = root["version"]
  if (typeof version !== "number" || !Number.isFinite(version)) return null

  const config: {
    version: number
    default?: { readonly mcpTools: readonly string[] | "*" }
    projects?: Record<string, { readonly mcpTools: readonly string[] | "*" }>
  } = { version }

  const defaultEntry = parseProjectEntry(root["default"])
  if (defaultEntry) {
    config.default = defaultEntry
  }

  if (root["projects"] && typeof root["projects"] === "object" && !Array.isArray(root["projects"])) {
    const projects: Record<string, { readonly mcpTools: readonly string[] | "*" }> = {}
    for (const [key, value] of Object.entries(root["projects"] as Record<string, unknown>)) {
      const entry = parseProjectEntry(value)
      if (entry) {
        projects[key.trim()] = entry
      }
    }
    if (Object.keys(projects).length > 0) {
      config.projects = projects
    }
  }

  return config
}

export function loadWechatToolAllowlistFromPath(path: string): WechatToolAllowlistConfig | null {
  try {
    const text = readFileSync(resolve(path), "utf8")
    return parseWechatToolAllowlistJson(text)
  } catch {
    return null
  }
}

export function wechatToolAllowlistPath(env: NodeJS.ProcessEnv = process.env): string {
  return (env["BUTLER_V5_WECHAT_TOOL_ALLOWLIST_PATH"] ?? "").trim()
}

/**
 * When BUTLER_V5_WECHAT_TOOL_ALLOWLIST_PATH is set, return allowed tool names
 * for the WeChat loop; otherwise undefined (expose full tool surface).
 */
export function resolveWechatAllowedToolNames(args: {
  readonly projectId: string
  readonly env?: NodeJS.ProcessEnv
  readonly mcpBundle?: McpToolBundle
}): readonly string[] | undefined {
  const env = args.env ?? process.env
  const path = wechatToolAllowlistPath(env)
  if (!path) return undefined

  const config = loadWechatToolAllowlistFromPath(path)
  if (!config) return undefined

  const mcpBundle = args.mcpBundle
  const availableMcpCapabilities = (mcpBundle?.runtimeTools ?? []).map((tool) => tool.name as string)
  return buildWechatAllowedToolNames({
    config,
    projectId: args.projectId,
    availableMcpCapabilities,
    includeSubagent: isSubagentEnabled(env),
  })
}
