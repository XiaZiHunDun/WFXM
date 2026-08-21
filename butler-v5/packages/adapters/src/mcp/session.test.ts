import { describe, expect, it, vi } from "vitest"
import {
  buildMcpInitializeRequest,
  captureMcpSessionId,
  isMcpNotification,
  mcpSessionHeaders,
} from "./session.js"

describe("MCP session helpers", () => {
  it("detects notification methods", () => {
    expect(isMcpNotification("notifications/initialized")).toBe(true)
    expect(isMcpNotification("tools/list")).toBe(false)
  })

  it("captures Mcp-Session-Id header", () => {
    const session: { id?: string } = {}
    captureMcpSessionId(session, { "Mcp-Session-Id": "sess-1" })
    expect(session.id).toBe("sess-1")
    expect(mcpSessionHeaders(session)).toEqual({ "mcp-session-id": "sess-1" })
  })

  it("builds initialize request with defaults", () => {
    expect(buildMcpInitializeRequest().method).toBe("initialize")
    expect(buildMcpInitializeRequest().params.clientInfo.name).toBe("butler-v5")
  })
})

describe("MCP client initialize handshake", () => {
  it("runs initialize before tools/list", async () => {
    const { makeMcpClientAdapter } = await import("./client.js")
    const calls: string[] = []
    const transport = {
      request: vi.fn(async (req: unknown) => {
        const r = req as { method: string }
        calls.push(r.method)
        if (r.method === "initialize") {
          return { result: { protocolVersion: "2024-11-05", capabilities: {} } }
        }
        if (r.method === "notifications/initialized") {
          return { result: null }
        }
        if (r.method === "tools/list") {
          return { result: { tools: [{ name: "ping", description: "d", inputSchema: {} }] } }
        }
        throw new Error(`unexpected ${r.method}`)
      }),
      close: vi.fn(async () => {}),
    }
    const adapter = makeMcpClientAdapter({ transport: transport as never })
    const tools = await adapter.discover()
    expect(tools.map((t) => t.name)).toEqual(["ping"])
    expect(calls).toEqual(["initialize", "notifications/initialized", "tools/list"])
  })
})
