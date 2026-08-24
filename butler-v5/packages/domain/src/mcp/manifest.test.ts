import { describe, expect, it } from "vitest"
import { findMcpServer, mcpServerIds, parseMcpManifest, resolveManifestStdioArgs } from "./manifest.js"

describe("MCP manifest", () => {
  it("parses server entries", () => {
    const parsed = parseMcpManifest({
      version: 1,
      servers: [
        {
          id: "local",
          transport: "stdio",
          command: "node",
          tools: [{ name: "search", risk: "high" }],
        },
      ],
    })
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return
    expect(mcpServerIds(parsed.value)).toEqual(["local"])
    expect(findMcpServer(parsed.value, "local")?.command).toBe("node")
    expect(parsed.value.servers[0]?.tools?.[0]?.name).toBe("search")
  })

  it("rejects invalid transport", () => {
    expect(
      parseMcpManifest({ version: 1, servers: [{ id: "x", transport: "ws" }] }).ok,
    ).toBe(false)
  })

  it("resolves --openapi-spec paths relative to manifest directory", () => {
    const resolved = resolveManifestStdioArgs("/repo/butler-v5/config/mcp-manifest.json", [
      "--api-base-url",
      "https://api.todoist.com",
      "--openapi-spec",
      "openapi/todoist-v1-readonly.yml",
    ])
    expect(resolved).toEqual([
      "--api-base-url",
      "https://api.todoist.com",
      "--openapi-spec",
      "/repo/butler-v5/config/openapi/todoist-v1-readonly.yml",
    ])
  })

  it("leaves absolute --openapi-spec paths unchanged", () => {
    const abs = "/abs/todoist.yml"
    const resolved = resolveManifestStdioArgs("/repo/config/mcp.json", ["--openapi-spec", abs])
    expect(resolved).toEqual(["--openapi-spec", abs])
  })
})
