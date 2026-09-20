import { describe, expect, it } from "vitest"
import type { McpManifestServer } from "@butler/domain/mcp/manifest.js"
import {
  isBlockedInboundHost,
  isBlockedMcpHost,
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

// D73 SEC-003: IPv6 ULA prefix match must restrict to actual IPv6
// literal hostnames (containing ':' or wrapped in '[...]') so public
// hostnames that happen to start with "fc" / "fd" are not false-positive
// blocked. Before the fix, `host.startsWith("fc")` matched any string
// starting with those two letters — silently blocking public
// hostnames like `fc-public-mcp.example.com`.
describe("isBlockedMcpHost / isBlockedInboundHost — IPv6 ULA prefix (D73 SEC-003)", () => {
  it("does NOT block public hostnames that start with 'fc'", () => {
    expect(isBlockedMcpHost("fc-public-mcp.example.com")).toBe(false)
    expect(isBlockedInboundHost("fc-public-mcp.example.com")).toBe(false)
  })

  it("does NOT block public hostnames that start with 'fd'", () => {
    expect(isBlockedMcpHost("fdashboards.example.com")).toBe(false)
    expect(isBlockedInboundHost("fdashboards.example.com")).toBe(false)
  })

  it("still blocks actual IPv6 ULA literal hostnames (fc00::/7)", () => {
    expect(isBlockedMcpHost("fc00:1234::1")).toBe(true)
    expect(isBlockedMcpHost("fd00:abcd::1")).toBe(true)
    expect(isBlockedMcpHost("[fc00::1]:8080")).toBe(true)
    expect(isBlockedInboundHost("fc00:1234::1")).toBe(true)
    expect(isBlockedInboundHost("[fd00::1]")).toBe(true)
  })
})
