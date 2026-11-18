import { describe, expect, it, vi } from "vitest"
import { makeMcpStdioTransport } from "./stdio-transport.js"
import { makeMcpClientAdapter } from "./client.js"

describe("MCP stdio transport", () => {
  it("exchanges newline-delimited JSON-RPC over stdin/stdout", async () => {
    let lineHandler: ((line: string) => void) | null = null
    const spawn = vi.fn(() => ({
      writeLine: (line: string) => {
        const msg = JSON.parse(line) as { id?: number; method: string }
        if (msg.method === "initialize" && typeof msg.id === "number") {
          lineHandler?.(
            JSON.stringify({
              jsonrpc: "2.0",
              id: msg.id,
              result: { protocolVersion: "2024-11-05", capabilities: {} },
            }),
          )
          return
        }
        if (msg.method === "notifications/initialized") {
          return
        }
        if (msg.method === "tools/list" && typeof msg.id === "number") {
          lineHandler?.(
            JSON.stringify({
              jsonrpc: "2.0",
              id: msg.id,
              result: {
                tools: [{ name: "ping", description: "pong", inputSchema: { type: "object" } }],
              },
            }),
          )
        }
      },
      onLine: (handler: (line: string) => void) => {
        lineHandler = handler
      },
      kill: vi.fn(),
    }))
    const transport = makeMcpStdioTransport({
      command: "mock-mcp",
      args: [],
      spawn: spawn as never,
    })
    const client = makeMcpClientAdapter({ transport })
    const tools = await client.discover()
    expect(tools).toHaveLength(1)
    expect(tools[0]?.name).toBe("ping")
    await transport.close()
    expect(spawn).toHaveBeenCalled()
  })
})
