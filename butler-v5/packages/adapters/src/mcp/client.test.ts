import { describe, expect, it, vi } from "vitest"
import { makeMcpClientAdapter } from "./client.js"

describe("MCP client adapter", () => {
  it("discover returns parsed tools", async () => {
    const transport = {
      request: vi.fn(async (req: unknown) => {
        const r = req as { method: string }
        if (r.method === "tools/list") {
          return {
            result: {
              tools: [
                { name: "echo", description: "echoes", inputSchema: { type: "object" } },
                { name: "search", description: "searches", inputSchema: { type: "object" } },
              ],
            },
          }
        }
        throw new Error("unexpected")
      }),
      close: vi.fn(async () => {}),
    }
    const adapter = makeMcpClientAdapter({ transport: transport as never })
    const tools = await adapter.discover()
    expect(tools.length).toBe(2)
    expect(tools[0]?.name).toBe("echo")
    expect(transport.close).not.toHaveBeenCalled()
  })

  it("invalidate closes the transport", async () => {
    const transport = {
      request: vi.fn(async () => ({ result: { tools: [] } })),
      close: vi.fn(async () => {}),
    }
    const adapter = makeMcpClientAdapter({ transport: transport as never })
    await adapter.invalidate("any-server")
    expect(transport.close).toHaveBeenCalledTimes(1)
  })

  it("discover propagates transport errors as rejections", async () => {
    const transport = {
      request: vi.fn(async () => {
        throw new Error("mcp-down")
      }),
      close: vi.fn(async () => {}),
    }
    const adapter = makeMcpClientAdapter({ transport: transport as never })
    await expect(adapter.discover()).rejects.toThrow(/mcp-down/)
  })

  it("invoke returns structured errors from MCP isError", async () => {
    const transport = {
      request: vi.fn(async () => ({
        result: {
          isError: true,
          content: [{ type: "text", text: "denied" }],
        },
      })),
      close: vi.fn(async () => {}),
    }
    const adapter = makeMcpClientAdapter({ transport: transport as never })
    const result = await adapter.invoke("bad", {})
    expect(result).toEqual({ ok: false, reason: "denied" })
  })
})
