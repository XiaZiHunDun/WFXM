import { describe, expect, it } from "vitest"
import { makeMcpToolDefinition } from "./mcp-tools.js"
import { makeToolExecutor, resolveOwnerSubject, toolTimeoutMs } from "./tool-boundary.js"
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

  it("uses MCP timeout for mcp_* tools", () => {
    const prev = process.env["BUTLER_V5_MCP_TIMEOUT_MS"]
    process.env["BUTLER_V5_MCP_TIMEOUT_MS"] = "90000"
    try {
      expect(toolTimeoutMs("mcp_todoist_lst-projects")).toBe(90000)
      expect(toolTimeoutMs("read_file")).toBe(5000)
    } finally {
      if (prev === undefined) delete process.env["BUTLER_V5_MCP_TIMEOUT_MS"]
      else process.env["BUTLER_V5_MCP_TIMEOUT_MS"] = prev
    }
  })

  it("extends run_command timeout under bubblewrap+slirp", () => {
    const prev = {
      sandbox: process.env["BUTLER_V5_SANDBOX"],
      egress: process.env["BUTLER_V5_SANDBOX_EGRESS_ISOLATION"],
      custom: process.env["BUTLER_V5_RUN_COMMAND_TIMEOUT_MS"],
    }
    process.env["BUTLER_V5_SANDBOX"] = "bubblewrap"
    process.env["BUTLER_V5_SANDBOX_EGRESS_ISOLATION"] = "slirp"
    delete process.env["BUTLER_V5_RUN_COMMAND_TIMEOUT_MS"]
    try {
      expect(toolTimeoutMs("run_command")).toBe(120_000)
      process.env["BUTLER_V5_RUN_COMMAND_TIMEOUT_MS"] = "45000"
      expect(toolTimeoutMs("run_command")).toBe(45_000)
    } finally {
      if (prev.sandbox === undefined) delete process.env["BUTLER_V5_SANDBOX"]
      else process.env["BUTLER_V5_SANDBOX"] = prev.sandbox
      if (prev.egress === undefined) delete process.env["BUTLER_V5_SANDBOX_EGRESS_ISOLATION"]
      else process.env["BUTLER_V5_SANDBOX_EGRESS_ISOLATION"] = prev.egress
      if (prev.custom === undefined) delete process.env["BUTLER_V5_RUN_COMMAND_TIMEOUT_MS"]
      else process.env["BUTLER_V5_RUN_COMMAND_TIMEOUT_MS"] = prev.custom
    }
  })
})
