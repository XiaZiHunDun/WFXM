import { describe, expect, it } from "vitest"
import {
  assertMcpServerConsented,
  loadMcpManifestFromJson,
  manifestAllowsServer,
  mcpServerIdFromEnv,
} from "./mcp-consent.js"

describe("MCP consent", () => {
  it("allows server when consent not required", () => {
    expect(assertMcpServerConsented("local", {})).toEqual({ ok: true })
  })

  it("blocks unlisted server when consent required", () => {
    expect(
      assertMcpServerConsented("remote", {
        BUTLER_V5_MCP_REQUIRE_CONSENT: "1",
        BUTLER_V5_MCP_CONSENT: "local",
      }),
    ).toMatchObject({ ok: false })
  })

  it("derives server id from MCP URL", () => {
    expect(
      mcpServerIdFromEnv({ BUTLER_V5_MCP_URL: "https://tools.example.com/mcp" }),
    ).toBe("tools.example.com")
  })

  it("loads manifest json", () => {
    const loaded = loadMcpManifestFromJson(
      JSON.stringify({ version: 1, servers: [{ id: "local", transport: "stdio" }] }),
    )
    expect(loaded.ok).toBe(true)
    if (loaded.ok) {
      expect(manifestAllowsServer(loaded.manifest, "local")).toBe(true)
    }
  })
})
