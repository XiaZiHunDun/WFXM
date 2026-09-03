import { describe, expect, it, vi } from "vitest"
import { loadMcpLlmTools, loadMcpToolDefinitions } from "./mcp-tools.js"

describe("mcp-tools opt-in", () => {
  it("returns no tools when MCP is disabled", () => {
    expect(loadMcpToolDefinitions({ BUTLER_V5_MCP_ENABLED: "0" })).toEqual([])
    expect(loadMcpLlmTools({ BUTLER_V5_MCP_ENABLED: "0" })).toEqual([])
  })

  it("registers stub MCP tools when enabled with BUTLER_V5_MCP_TOOL_NAMES", () => {
    const env = { BUTLER_V5_MCP_ENABLED: "1", BUTLER_V5_MCP_TOOL_NAMES: "search,fetch" }
    const tools = loadMcpToolDefinitions(env)
    expect(tools.map((t) => t.name)).toEqual(["mcp_search", "mcp_fetch"])
    expect(tools.every((t) => t.risk === "high")).toBe(true)
    const llm = loadMcpLlmTools(env)
    expect(llm.map((t) => t.name)).toEqual(["mcp_search", "mcp_fetch"])
  })

  it("invokes injected handler for discovered tools", async () => {
    const invoke = vi.fn(async () => ({ ok: true as const, output: "done" }))
    const tools = loadMcpToolDefinitions(
      { BUTLER_V5_MCP_ENABLED: "1" },
      { discovered: [{ name: "ping" }], invoke },
    )
    const tool = tools[0]
    expect(tool).toBeDefined()
    if (!tool) return
    const result = await tool.run({})
    expect(result).toEqual({ ok: true, output: "done" })
    expect(invoke).toHaveBeenCalledWith("ping", {})
  })

  it("P3-2: discovered MCP tool declares its inputSchema when present", async () => {
    const invoke = vi.fn(async () => ({ ok: true as const, output: "done" }))
    const tools = loadMcpToolDefinitions(
      { BUTLER_V5_MCP_ENABLED: "1" },
      {
        discovered: [{ name: "weather", inputSchema: { type: "object", city: { type: "string" } } }],
        invoke,
      },
    )
    const tool = tools[0]
    expect(tool?.declared?.inputSchema).toEqual({
      type: "object",
      city: { type: "string" },
    })
    // MCP opts into summary audit; resolved by capability-boundary against command kind.
    expect(tool?.declared?.auditPolicy).toBe("summary")
  })

  it("P3-2: discovered MCP tool declares its outputSchema when present", async () => {
    const invoke = vi.fn(async () => ({ ok: true as const, output: "done" }))
    const tools = loadMcpToolDefinitions(
      { BUTLER_V5_MCP_ENABLED: "1" },
      {
        discovered: [{ name: "weather", inputSchema: { type: "object" }, outputSchema: { type: "object" } }],
        invoke,
      },
    )
    const tool = tools[0]
    expect(tool?.declared?.inputSchema).toEqual({ type: "object" })
    expect(tool?.declared?.outputSchema).toEqual({ type: "object" })
  })
})
