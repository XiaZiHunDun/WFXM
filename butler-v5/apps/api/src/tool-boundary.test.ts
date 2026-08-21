import { describe, expect, it } from "vitest"
import { makeMcpToolDefinition } from "./mcp-tools.js"
import { makeToolExecutor, resolveOwnerSubject } from "./tool-boundary.js"
import type { ToolDefinition } from "@butler/runtime/tool-runtime.js"

describe("tool-boundary", () => {
  it("resolveOwnerSubject prefers BUTLER_OWNER_WECHAT_ID", () => {
    expect(
      resolveOwnerSubject({ BUTLER_OWNER_WECHAT_ID: "owner-a, owner-b" }, "fallback"),
    ).toBe("owner-a")
    expect(resolveOwnerSubject({}, "fallback")).toBe("fallback")
  })

  it("makeToolExecutor routes through policy gate", async () => {
    const def: ToolDefinition = {
      name: "get_current_time" as ToolDefinition["name"],
      risk: "low",
      run: async () => ({ ok: true, output: "t" }),
    }
    const executor = makeToolExecutor({
      tools: [def],
      ownerSubject: "owner-1",
      subject: "guest-1",
      conversationId: "conv-1",
      timeoutMsFor: () => 1000,
    })
    const result = await executor.execute(def, {})
    expect(result.ok).toBe(true)
    if (result.ok) {
      expect(result.output).toBe("t")
    }
  })

  it("routes MCP tools through extra provider registration", async () => {
    const mcpDef = makeMcpToolDefinition(
      { name: "search", description: "search" },
      async () => ({ ok: true, output: "mcp-hit" }),
    )
    const executor = makeToolExecutor({
      tools: [mcpDef],
      ownerSubject: "owner-1",
      subject: "owner-1",
      conversationId: "conv-1",
      timeoutMsFor: () => 1000,
    })
    expect(executor.registry.get("mcp_search")).toEqual({
      name: "mcp_search",
      kind: "command",
      risk: "high",
    })
    const result = await executor.execute(mcpDef, { q: "hello" })
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.reason).toContain("[需要确认]")
      expect(result.reason).toContain("mcp_search")
    }
  })
})
