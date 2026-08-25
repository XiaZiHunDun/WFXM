import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"
import { toMcpCapabilityNameForServer } from "@butler/domain/governance/mcp-tool-capability.js"
import { parseWechatToolAllowlistJson } from "./wechat-tool-allowlist.js"

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "../../..")

function loadJson<T>(relativePath: string): T {
  const text = readFileSync(join(repoRoot, relativePath), "utf8")
  return JSON.parse(text) as T
}

type ManifestTool = { readonly name: string }
type ManifestServer = {
  readonly id: string
  readonly tools?: readonly ManifestTool[]
}

describe("MCP production hardening configs", () => {
  it("limits github manifest to read-only tool names", () => {
    const manifest = loadJson<{ servers: readonly ManifestServer[] }>("config/mcp-manifest.json")
    const github = manifest.servers.find((s) => s.id === "github")
    expect(github).toBeDefined()
    const names = (github?.tools ?? []).map((t) => t.name)
    expect(names.length).toBeGreaterThan(0)
    expect(names.length).toBeLessThanOrEqual(14)
    for (const name of names) {
      expect(name).toMatch(/^(search_|get_|list_)/)
      expect(name).not.toMatch(/^(create_|update_|delete_|push_|merge_|fork_|add_|remove_)/)
    }
  })

  it("wechat allowlist mcpTools are subset of manifest capabilities", () => {
    const manifest = loadJson<{ servers: readonly ManifestServer[] }>("config/mcp-manifest.json")
    const manifestCaps = new Set<string>()
    for (const server of manifest.servers) {
      for (const tool of server.tools ?? []) {
        const cap = toMcpCapabilityNameForServer(server.id, tool.name)
        if (cap) manifestCaps.add(cap)
      }
    }
    const allowlist = parseWechatToolAllowlistJson(
      readFileSync(join(repoRoot, "config/wechat-tool-allowlist.json"), "utf8"),
    )
    expect(allowlist).not.toBeNull()
    if (!allowlist) return

    expect(allowlist.default?.mcpTools).toEqual([])

    const wechatEntry = allowlist.projects?.["wechat"]
    expect(wechatEntry?.mcpTools).not.toBe("*")
    if (Array.isArray(wechatEntry?.mcpTools)) {
      for (const cap of wechatEntry.mcpTools) {
        expect(manifestCaps.has(cap)).toBe(true)
      }
      expect(wechatEntry.mcpTools.length).toBe(manifestCaps.size)
    }
  })
})
