import { describe, expect, it, vi } from "vitest"
import { makeMcpHttpTransport } from "./http-transport.js"
import { makeMcpClientAdapter } from "./client.js"

function mcpFetchMock() {
  return vi.fn(async (_url: string, init?: RequestInit) => {
    const body = JSON.parse(String(init?.body)) as { method: string; id?: number }
    if (body.method === "initialize") {
      return new Response(
        JSON.stringify({
          jsonrpc: "2.0",
          id: body.id,
          result: { protocolVersion: "2024-11-05", capabilities: {} },
        }),
        {
          status: 200,
          headers: {
            "content-type": "application/json",
            "Mcp-Session-Id": "sess-http-1",
          },
        },
      )
    }
    if (body.method === "notifications/initialized") {
      return new Response("", { status: 202 })
    }
    if (body.method === "tools/list") {
      expect(init?.headers).toMatchObject({ "mcp-session-id": "sess-http-1" })
      return new Response(
        JSON.stringify({
          jsonrpc: "2.0",
          id: body.id,
          result: {
            tools: [{ name: "ping", description: "pong", inputSchema: { type: "object" } }],
          },
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      )
    }
    if (body.method === "tools/call") {
      return new Response(
        JSON.stringify({
          jsonrpc: "2.0",
          id: body.id,
          result: {
            content: [{ type: "text", text: "hello from mcp" }],
          },
        }),
        { status: 200 },
      )
    }
    throw new Error(`unexpected ${body.method}`)
  })
}

describe("MCP HTTP transport", () => {
  it("posts JSON-RPC tools/list and parses tools", async () => {
    const fetchMock = mcpFetchMock()
    const transport = makeMcpHttpTransport({
      url: "http://127.0.0.1:7777/mcp",
      fetch: fetchMock as typeof fetch,
    })
    const client = makeMcpClientAdapter({ transport })
    const tools = await client.discover()
    expect(tools).toHaveLength(1)
    expect(tools[0]?.name).toBe("ping")
  })

  it("tools/call extracts text content", async () => {
    const fetchMock = mcpFetchMock()
    const client = makeMcpClientAdapter({
      transport: makeMcpHttpTransport({
        url: "http://127.0.0.1:7777/mcp",
        fetch: fetchMock as typeof fetch,
      }),
    })
    const result = await client.invoke("echo", { msg: "hi" })
    expect(result).toEqual({ ok: true, output: "hello from mcp" })
  })
})
