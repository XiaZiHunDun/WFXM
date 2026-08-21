import { describe, expect, it } from "vitest"
import { mcpServerIds, parseMcpManifest } from "./manifest.js"

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
    expect(parsed.value.servers[0]?.tools?.[0]?.name).toBe("search")
  })

  it("rejects invalid transport", () => {
    expect(
      parseMcpManifest({ version: 1, servers: [{ id: "x", transport: "ws" }] }).ok,
    ).toBe(false)
  })
})
