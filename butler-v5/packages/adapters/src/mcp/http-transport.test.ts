import { describe, expect, it, vi } from "vitest"
import { makeMcpHttpTransport } from "./http-transport.js"
import { makeMcpClientAdapter } from "./client.js"

describe("MCP HTTP transport", () => {
  it("posts JSON-RPC tools/list and parses tools", async () => {
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body)) as { method: string }
      expect(body.method).toBe("tools/list")
      return new Response(
        JSON.stringify({
          jsonrpc: "2.0",
          id: 1,
          result: {
            tools: [{ name: "ping", description: "pong", inputSchema: { type: "object" } }],
          },
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      )
    })
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
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body)) as { method: string; params: unknown }
      expect(body.method).toBe("tools/call")
      return new Response(
        JSON.stringify({
          jsonrpc: "2.0",
          id: 2,
          result: {
            content: [{ type: "text", text: "hello from mcp" }],
          },
        }),
        { status: 200 },
      )
    })
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
