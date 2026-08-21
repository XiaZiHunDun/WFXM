import { describe, expect, it } from "vitest"
import type { McpManifestServer } from "@butler/domain/mcp/manifest.js"
import {
  mcpHasServerEndpoint,
  parseMcpConnectionConfig,
  parseMcpTransportKind,
} from "./mcp-config.js"

const httpManifestServer: McpManifestServer = {
  id: "tools.example.com",
  transport: "http",
  url: "http://127.0.0.1:7777/mcp",
}

describe("parseMcpConnectionConfig", () => {
  it("uses manifest url when env url is unset", () => {
    const parsed = parseMcpConnectionConfig(
      {
        BUTLER_V5_MCP_ENABLED: "1",
      },
      httpManifestServer,
    )
    expect(parsed).toEqual({
      ok: true,
      value: {
        kind: "http",
        url: "http://127.0.0.1:7777/mcp",
        timeoutMs: 30_000,
      },
    })
  })

  it("prefers env url over manifest", () => {
    const parsed = parseMcpConnectionConfig(
      {
        BUTLER_V5_MCP_ENABLED: "1",
        BUTLER_V5_MCP_URL: "http://127.0.0.1:9999/mcp",
      },
      httpManifestServer,
    )
    expect(parsed.ok).toBe(true)
    if (parsed.ok) {
      expect(parsed.value.url).toBe("http://127.0.0.1:9999/mcp")
    }
  })

  it("uses manifest transport when env transport is unset", () => {
    expect(parseMcpTransportKind({}, { id: "x", transport: "sse" })).toBe("sse")
  })

  it("detects manifest endpoint for stub fallback", () => {
    expect(mcpHasServerEndpoint({}, httpManifestServer)).toBe(true)
  })
})
