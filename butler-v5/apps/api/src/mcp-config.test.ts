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

  it("resolves manifest-relative --openapi-spec for stdio transport", () => {
    const todoistServer: McpManifestServer = {
      id: "todoist",
      transport: "stdio",
      command: "openapi-mcp-server",
      args: [
        "--api-base-url",
        "https://api.todoist.com",
        "--openapi-spec",
        "openapi/todoist-v1-readonly.yml",
      ],
    }
    const parsed = parseMcpConnectionConfig(
      {
        BUTLER_V5_MCP_ENABLED: "1",
        BUTLER_V5_MCP_MANIFEST_PATH: "/repo/butler-v5/config/mcp-manifest.json",
      },
      todoistServer,
      { serverId: "todoist" },
    )
    expect(parsed.ok).toBe(true)
    if (!parsed.ok || parsed.value.kind !== "stdio") return
    expect(parsed.value.args).toEqual([
      "--api-base-url",
      "https://api.todoist.com",
      "--openapi-spec",
      "/repo/butler-v5/config/openapi/todoist-v1-readonly.yml",
    ])
  })
})
