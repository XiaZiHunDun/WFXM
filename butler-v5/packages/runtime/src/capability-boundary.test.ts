import { describe, expect, it, vi } from "vitest"
import {
  actionKindForTool,
  buildCapabilityRegistryFromTools,
  executeToolThroughBoundary,
  resourceForTool,
} from "./capability-boundary.js"
import { defaultPermissionPolicy, PolicyGate } from "./policy-gate.js"
import type { ToolDefinition } from "./tool-runtime.js"

describe("capability-boundary", () => {
  it("maps tool names to action kinds", () => {
    expect(actionKindForTool("run_command")).toBe("command")
    expect(actionKindForTool("send_wechat_file")).toBe("outbound")
    expect(actionKindForTool("delegate_to_subagent")).toBe("delegate")
    expect(actionKindForTool("read_file")).toBe("read")
  })

  it("derives resource from tool args", () => {
    expect(resourceForTool("read_file", { path: "docs/a.md" }, "conv-1")).toBe("docs/a.md")
    expect(resourceForTool("run_command", { argv: ["ls", "-la"] }, "conv-1")).toBe("ls -la")
    expect(resourceForTool("get_current_time", {}, "conv-1")).toBe("conv-1")
  })

  it("blocks high-risk command for non-owner subject", async () => {
    const def: ToolDefinition = {
      name: "run_command" as ToolDefinition["name"],
      risk: "high",
      run: vi.fn(async () => ({ ok: true, output: "ok" })),
    }
    const registry = buildCapabilityRegistryFromTools([def])
    const gate = new PolicyGate(defaultPermissionPolicy("owner-1"), () => 1000)
    const outcome = await executeToolThroughBoundary(
      registry,
      gate,
      def,
      { argv: ["pwd"] },
      { subject: "guest-1", resource: "pwd", grant: null },
    )
    expect(outcome.ok).toBe(false)
    if (!outcome.ok) {
      expect(outcome.reason).toContain("policy denied")
    }
  })

  it("returns Ask envelope for alwaysConfirm capabilities", async () => {
    const def: ToolDefinition = {
      name: "send_wechat_file" as ToolDefinition["name"],
      risk: "medium",
      run: vi.fn(async () => ({ ok: true, output: "sent" })),
    }
    const registry = buildCapabilityRegistryFromTools([def])
    const gate = new PolicyGate(defaultPermissionPolicy("owner-1"), () => 1000)
    const outcome = await executeToolThroughBoundary(
      registry,
      gate,
      def,
      { path: "a.jpg" },
      { subject: "owner-1", resource: "a.jpg", grant: null },
    )
    expect(outcome.ok).toBe(false)
    if (!outcome.ok) {
      expect(outcome.reason).toContain("[需要确认]")
    }
    expect(def.run).not.toHaveBeenCalled()
  })

  it("executes low-risk read tools for any subject", async () => {
    const def: ToolDefinition = {
      name: "get_current_time" as ToolDefinition["name"],
      risk: "low",
      run: vi.fn(async () => ({ ok: true, output: "now" })),
    }
    const registry = buildCapabilityRegistryFromTools([def])
    const gate = new PolicyGate(defaultPermissionPolicy("owner-1"), () => 1000)
    const outcome = await executeToolThroughBoundary(
      registry,
      gate,
      def,
      {},
      { subject: "guest-1", resource: "conv-1", grant: null },
    )
    expect(outcome).toEqual({ ok: true, output: "now" })
  })
})
