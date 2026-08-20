import { describe, expect, it, vi } from "vitest"
import { bootstrapMcpTools } from "./mcp-bootstrap.js"

describe("bootstrapMcpTools", () => {
  it("returns off bundle when MCP disabled", async () => {
    const bundle = await bootstrapMcpTools({ BUTLER_V5_MCP_ENABLED: "0" })
    expect(bundle.mode).toBe("off")
    expect(bundle.runtimeTools).toEqual([])
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
    const fetchMock = vi.fn(async () =>
      Response.json({
        jsonrpc: "2.0",
        id: 1,
        result: {
          tools: [{ name: "echo", description: "echo tool", inputSchema: { type: "object" } }],
        },
      }),
    )
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

  it("discovers tools over injected stdio transport", async () => {
    const transport = {
      request: async (req: unknown) => {
        const msg = req as { method: string }
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
})
