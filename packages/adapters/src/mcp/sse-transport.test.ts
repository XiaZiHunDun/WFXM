import { describe, expect, it, vi } from "vitest"
import { makeMcpSseTransport } from "./sse-transport.js"
import { makeMcpClientAdapter } from "./client.js"

function mcpSseFetchMock(streamBody: string) {
  return vi.fn(async (_url: string, init?: RequestInit) => {
    const body = JSON.parse(String(init?.body)) as { method: string; id?: number }
    if (body.method === "initialize") {
      return new Response(
        JSON.stringify({
          jsonrpc: "2.0",
          id: body.id,
          result: { protocolVersion: "2024-11-05", capabilities: {} },
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      )
    }
    if (body.method === "notifications/initialized") {
      return new Response("", { status: 202 })
    }
    if (body.method === "tools/list") {
      return new Response(streamBody, {
        status: 200,
        headers: { "content-type": "text/event-stream" },
      })
    }
    throw new Error(`unexpected ${body.method}`)
  })
}

describe("MCP SSE transport", () => {
  it("parses SSE data events for tools/list", async () => {
    const fetchMock = mcpSseFetchMock(
      'event: message\ndata: {"jsonrpc":"2.0","id":2,"result":{"tools":[{"name":"echo","description":"d","inputSchema":{"type":"object"}}]}}\n\n',
    )
    const client = makeMcpClientAdapter({
      transport: makeMcpSseTransport({
        url: "http://127.0.0.1:7777/sse",
        fetch: fetchMock as typeof fetch,
      }),
    })
    const tools = await client.discover()
    expect(tools.map((t) => t.name)).toEqual(["echo"])
  })

  it("accepts JSON responses when server does not stream", async () => {
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
        result: { tools: [{ name: "one", description: "d", inputSchema: {} }] },
      })
    })
    const client = makeMcpClientAdapter({
      transport: makeMcpSseTransport({
        url: "http://127.0.0.1:7777/sse",
        fetch: fetchMock as typeof fetch,
      }),
    })
    const tools = await client.discover()
    expect(tools[0]?.name).toBe("one")
  })
})
