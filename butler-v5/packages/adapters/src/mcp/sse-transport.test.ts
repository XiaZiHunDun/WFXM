import { describe, expect, it, vi } from "vitest"
import { makeMcpSseTransport } from "./sse-transport.js"
import { makeMcpClientAdapter } from "./client.js"

describe("MCP SSE transport", () => {
  it("parses SSE data events for tools/list", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"tools":[{"name":"echo","description":"d","inputSchema":{"type":"object"}}]}}\n\n',
        { status: 200, headers: { "content-type": "text/event-stream" } },
      ),
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
    const fetchMock = vi.fn(async () =>
      Response.json({
        jsonrpc: "2.0",
        id: 1,
        result: { tools: [{ name: "one", description: "d", inputSchema: {} }] },
      }),
    )
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
