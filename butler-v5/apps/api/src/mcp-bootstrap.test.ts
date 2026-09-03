import { mkdtempSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { describe, expect, it, vi } from "vitest"
import type { RuntimeStore } from "@butler/domain/runtime.js"
import { bootstrapMcpTools } from "./mcp-bootstrap.js"

describe("bootstrapMcpTools", () => {
  it("returns off bundle when MCP disabled", async () => {
    const bundle = await bootstrapMcpTools({ BUTLER_V5_MCP_ENABLED: "0" })
    expect(bundle.mode).toBe("off")
    expect(bundle.runtimeTools).toEqual([])
  })

  it("revokes MCP grants when MCP disabled and runtimeStore is wired", async () => {
    const revoke = vi.fn(async () => 1)
    const store = {
      revokeScopedGrantsForMcpServer: revoke,
    } as unknown as RuntimeStore
    await bootstrapMcpTools(
      {
        BUTLER_V5_MCP_ENABLED: "0",
        BUTLER_V5_MCP_SERVER_ID: "demo-server",
      },
      { runtimeStore: store },
    )
    expect(revoke).toHaveBeenCalledWith("demo-server", expect.any(Date))
  })

  it("loads stub tools without URL", async () => {
    const bundle = await bootstrapMcpTools({
      BUTLER_V5_MCP_ENABLED: "1",
      BUTLER_V5_MCP_TOOL_NAMES: "search",
    })
    expect(bundle.mode).toBe("stub")
    expect(bundle.runtimeTools.map((t) => t.name)).toEqual(["mcp_search"])
  })

  it("discovers HTTP MCP tools when URL is set", async () => {
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body)) as { method: string; id?: number }
      if (body.method === "initialize") {
        return Response.json({
          jsonrpc: "2.0",
          id: body.id,
          result: { protocolVersion: "2024-11-05", capabilities: {} },
        })
      }
      if (body.method === "notifications/initialized") {
        return new Response("", { status: 202 })
      }
      return Response.json({
        jsonrpc: "2.0",
        id: body.id,
        result: {
          tools: [{ name: "echo", description: "echo tool", inputSchema: { type: "object" } }],
        },
      })
    })
    const bundle = await bootstrapMcpTools(
      {
        BUTLER_V5_MCP_ENABLED: "1",
        BUTLER_V5_MCP_URL: "http://127.0.0.1:7777/mcp",
      },
      { fetch: fetchMock as typeof fetch },
    )
    expect(bundle.mode).toBe("http")
    expect(bundle.runtimeTools.map((t) => t.name)).toEqual(["mcp_echo"])
    expect(fetchMock).toHaveBeenCalled()
  })

  it("returns off when consent required but server not listed", async () => {
    const revoke = vi.fn(async () => 2)
    const store = {
      revokeScopedGrantsForMcpServer: revoke,
    } as unknown as RuntimeStore
    const bundle = await bootstrapMcpTools(
      {
        BUTLER_V5_MCP_ENABLED: "1",
        BUTLER_V5_MCP_TOOL_NAMES: "search",
        BUTLER_V5_MCP_REQUIRE_CONSENT: "1",
        BUTLER_V5_MCP_CONSENT: "other-server",
        BUTLER_V5_MCP_SERVER_ID: "blocked-server",
      },
      { runtimeStore: store },
    )
    expect(bundle.mode).toBe("off")
    expect(bundle.runtimeTools).toEqual([])
    expect(revoke).toHaveBeenCalledWith("blocked-server", expect.any(Date))
  })

  it("returns off when consent required but server not listed (no store)", async () => {
    const bundle = await bootstrapMcpTools({
      BUTLER_V5_MCP_ENABLED: "1",
      BUTLER_V5_MCP_TOOL_NAMES: "search",
      BUTLER_V5_MCP_REQUIRE_CONSENT: "1",
      BUTLER_V5_MCP_CONSENT: "other-server",
    })
    expect(bundle.mode).toBe("off")
    expect(bundle.runtimeTools).toEqual([])
  })

  it("returns off when manifest path excludes configured server", async () => {
    const dir = mkdtempSync(join(tmpdir(), "butler-mcp-bootstrap-"))
    const manifestPath = join(dir, "mcp.json")
    writeFileSync(
      manifestPath,
      JSON.stringify({
        version: 1,
        servers: [{ id: "allowed-only", transport: "stdio", command: "node" }],
      }),
    )
    const bundle = await bootstrapMcpTools({
      BUTLER_V5_MCP_ENABLED: "1",
      BUTLER_V5_MCP_TOOL_NAMES: "search",
      BUTLER_V5_MCP_SERVER_ID: "blocked-server",
      BUTLER_V5_MCP_MANIFEST_PATH: manifestPath,
    })
    expect(bundle.mode).toBe("off")
    expect(bundle.runtimeTools).toEqual([])
  })

  it("loads stub tools when manifest includes configured server", async () => {
    const dir = mkdtempSync(join(tmpdir(), "butler-mcp-bootstrap-"))
    const manifestPath = join(dir, "mcp.json")
    writeFileSync(
      manifestPath,
      JSON.stringify({
        version: 1,
        servers: [{ id: "local-stub", transport: "http" }],
      }),
    )
    const bundle = await bootstrapMcpTools({
      BUTLER_V5_MCP_ENABLED: "1",
      BUTLER_V5_MCP_TOOL_NAMES: "search",
      BUTLER_V5_MCP_SERVER_ID: "local-stub",
      BUTLER_V5_MCP_MANIFEST_PATH: manifestPath,
    })
    expect(bundle.mode).toBe("stub")
    expect(bundle.runtimeTools.map((t) => t.name)).toEqual(["mcp_search"])
  })

  it("discovers HTTP MCP tools from manifest url without env url", async () => {
    const dir = mkdtempSync(join(tmpdir(), "butler-mcp-bootstrap-"))
    const manifestPath = join(dir, "mcp.json")
    writeFileSync(
      manifestPath,
      JSON.stringify({
        version: 1,
        servers: [
          {
            id: "tools.example.com",
            transport: "http",
            url: "http://127.0.0.1:7777/mcp",
          },
        ],
      }),
    )
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body)) as { method: string; id?: number }
      if (body.method === "initialize") {
        return Response.json({
          jsonrpc: "2.0",
          id: body.id,
          result: { protocolVersion: "2024-11-05", capabilities: {} },
        })
      }
      if (body.method === "notifications/initialized") {
        return new Response("", { status: 202 })
      }
      return Response.json({
        jsonrpc: "2.0",
        id: body.id,
        result: {
          tools: [{ name: "manifest-echo", description: "from manifest", inputSchema: { type: "object" } }],
        },
      })
    })
    const bundle = await bootstrapMcpTools(
      {
        BUTLER_V5_MCP_ENABLED: "1",
        BUTLER_V5_MCP_SERVER_ID: "tools.example.com",
        BUTLER_V5_MCP_MANIFEST_PATH: manifestPath,
      },
      { fetch: fetchMock as typeof fetch },
    )
    expect(bundle.mode).toBe("http")
    expect(bundle.runtimeTools.map((t) => t.name)).toEqual(["mcp_manifest-echo"])
  })

  it("discovers tools over injected stdio transport", async () => {
    const transport = {
      request: async (req: unknown) => {
        const msg = req as { method: string }
        if (msg.method === "initialize") {
          return { result: { protocolVersion: "2024-11-05", capabilities: {} } }
        }
        if (msg.method === "notifications/initialized") {
          return { result: null }
        }
        if (msg.method === "tools/list") {
          return {
            result: {
              tools: [{ name: "stdio-tool", description: "d", inputSchema: { type: "object" } }],
            },
          }
        }
        return { result: { content: [{ type: "text", text: "ok" }] } }
      },
      close: async () => {},
    }
    const bundle = await bootstrapMcpTools(
      {
        BUTLER_V5_MCP_ENABLED: "1",
        BUTLER_V5_MCP_TRANSPORT: "stdio",
        BUTLER_V5_MCP_COMMAND: "node",
      },
      { transport },
    )
    expect(bundle.mode).toBe("stdio")
    expect(bundle.runtimeTools.map((t) => t.name)).toEqual(["mcp_stdio-tool"])
  })

  function httpEchoFetch() {
    return vi.fn(async (_url: string, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body)) as { method: string; id?: number }
      if (body.method === "initialize") {
        return Response.json({
          jsonrpc: "2.0",
          id: body.id,
          result: { protocolVersion: "2024-11-05", capabilities: {} },
        })
      }
      if (body.method === "notifications/initialized") {
        return new Response("", { status: 202 })
      }
      if (body.method === "tools/list") {
        return Response.json({
          jsonrpc: "2.0",
          id: body.id,
          result: {
            tools: [{ name: "echo", description: "echo", inputSchema: { type: "object" } }],
          },
        })
      }
      return Response.json({
        jsonrpc: "2.0",
        id: body.id,
        result: { content: [{ type: "text", text: "pong" }] },
      })
    })
  }

  it("P3-3: rejects tokenish args to remote http server without oauthAudience at invoke", async () => {
    const fetchMock = httpEchoFetch()
    const bundle = await bootstrapMcpTools(
      {
        BUTLER_V5_MCP_ENABLED: "1",
        BUTLER_V5_MCP_URL: "http://127.0.0.1:7777/mcp",
      },
      { fetch: fetchMock as typeof fetch },
    )
    const echo = bundle.runtimeTools[0]
    expect(echo).toBeDefined()
    if (!echo) return
    const out = await echo.run({ token: "sekrit" })
    expect(out.ok).toBe(false)
    if (!out.ok) {
      expect(out.reason).toContain("no token passthrough")
    }
    // client.invoke must NOT have been reached (no tools/call JSON-RPC).
    const callSent = fetchMock.mock.calls.some(([, init]) => {
      try {
        const body = JSON.parse(String(init?.body)) as { method: string }
        return body.method === "tools/call"
      } catch {
        return false
      }
    })
    expect(callSent).toBe(false)
  })

  it("P3-3: allows tokenish args to remote http server WITH manifest oauthAudience", async () => {
    const dir = mkdtempSync(join(tmpdir(), "butler-mcp-bootstrap-"))
    const manifestPath = join(dir, "mcp.json")
    writeFileSync(
      manifestPath,
      JSON.stringify({
        version: 1,
        servers: [
          {
            id: "secure.example.com",
            transport: "http",
            url: "http://127.0.0.1:7777/mcp",
            oauthAudience: "api.example.com",
          },
        ],
      }),
    )
    const fetchMock = httpEchoFetch()
    const bundle = await bootstrapMcpTools(
      {
        BUTLER_V5_MCP_ENABLED: "1",
        BUTLER_V5_MCP_SERVER_ID: "secure.example.com",
        BUTLER_V5_MCP_MANIFEST_PATH: manifestPath,
      },
      { fetch: fetchMock as typeof fetch },
    )
    const echo = bundle.runtimeTools[0]
    expect(echo).toBeDefined()
    if (!echo) return
    const out = await echo.run({ token: "aud-bound" })
    expect(out.ok).toBe(true)
    // invoke reaches client.invoke (tools/call)
    const callSent = fetchMock.mock.calls.some(([, init]) => {
      try {
        const body = JSON.parse(String(init?.body)) as { method: string }
        return body.method === "tools/call"
      } catch {
        return false
      }
    })
    expect(callSent).toBe(true)
  })
})
