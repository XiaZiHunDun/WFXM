import { describe, expect, it } from "vitest"
import { isMcpEnabled, mcpStubToolNames } from "./mcp-gate.js"

describe("mcp-gate", () => {
  it("isMcpEnabled is opt-in (default off, only literal '1' enables)", () => {
    expect(isMcpEnabled({})).toBe(false)
    expect(isMcpEnabled({ BUTLER_V5_MCP_ENABLED: "0" })).toBe(false)
    expect(isMcpEnabled({ BUTLER_V5_MCP_ENABLED: "true" })).toBe(false)
    expect(isMcpEnabled({ BUTLER_V5_MCP_ENABLED: " 1 " })).toBe(true)
  })

  it("mcpStubToolNames parses comma/space-separated names and drops empties", () => {
    expect(mcpStubToolNames({})).toEqual([])
    expect(mcpStubToolNames({ BUTLER_V5_MCP_TOOL_NAMES: "   " })).toEqual([])
    expect(mcpStubToolNames({ BUTLER_V5_MCP_TOOL_NAMES: "a, b ,,c" })).toEqual(["a", "b", "c"])
    expect(mcpStubToolNames({ BUTLER_V5_MCP_TOOL_NAMES: "x y z" })).toEqual(["x", "y", "z"])
  })
})
