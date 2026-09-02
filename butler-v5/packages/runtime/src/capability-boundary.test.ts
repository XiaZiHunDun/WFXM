import { describe, expect, it, vi } from "vitest"
import {
  actionKindForTool,
  buildCapabilityRegistryFromTools,
  createProductionCapabilityRegistry,
  executeToolThroughBoundary,
  mcpCapabilityProvidersFromTools,
  resourceForTool,
  splitCoreAndMcpTools,
  unregisterCapability,
} from "./capability-boundary.js"
import { defaultPermissionPolicy, PolicyGate, productionPermissionPolicy } from "./policy-gate.js"
import type { ToolDefinition } from "./tool-runtime.js"
import type { RuntimeStore } from "@butler/domain/runtime.js"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { makeTestDb } from "@butler/persistence/testing.js"

describe("capability-boundary", () => {
  it("unregisters a capability and revokes its grants through the store", async () => {
    const def: ToolDefinition = {
      name: "read_file" as ToolDefinition["name"],
      risk: "low",
      run: vi.fn(async () => ({ ok: true, output: "x" })),
    }
    const registry = buildCapabilityRegistryFromTools([def])
    const store = {
      revokeScopedGrantsForCapability: vi.fn(async () => 2),
    } as unknown as RuntimeStore
    expect(registry.isRegistered("read_file")).toBe(true)
    const first = await unregisterCapability({ registry, name: "read_file", store })
    expect(first).toEqual({ removed: true, revokedGrants: 2 })
    expect(store.revokeScopedGrantsForCapability).toHaveBeenCalledWith("read_file", expect.any(Date))
    expect(registry.isRegistered("read_file")).toBe(false)
    // No provider -> no store call on a second attempt.
    const second = await unregisterCapability({ registry, name: "read_file", store })
    expect(second).toEqual({ removed: false, revokedGrants: 0 })
  })

  it("maps tool names to action kinds", () => {
    expect(actionKindForTool("run_command")).toBe("command")
    expect(actionKindForTool("write_file")).toBe("write")
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

  it("returns Ask envelope for run_command", async () => {
    const def: ToolDefinition = {
      name: "run_command" as ToolDefinition["name"],
      risk: "high",
      run: vi.fn(async () => ({ ok: true, output: "ok" })),
    }
    const registry = buildCapabilityRegistryFromTools([def])
    const gate = new PolicyGate(productionPermissionPolicy("owner-1"), () => 1000)
    const outcome = await executeToolThroughBoundary(
      registry,
      gate,
      def,
      { argv: ["pwd"] },
      { subject: "owner-1", resource: "pwd", grant: null },
    )
    expect(outcome.ok).toBe(false)
    if (!outcome.ok) {
      expect(outcome.reason).toContain("[需要确认]")
    }
    expect(def.run).not.toHaveBeenCalled()
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

  it("registers extra providers via createProductionCapabilityRegistry", async () => {
    const base: ToolDefinition = {
      name: "get_current_time" as ToolDefinition["name"],
      risk: "low",
      run: vi.fn(async () => ({ ok: true, output: "now" })),
    }
    const registry = createProductionCapabilityRegistry({
      tools: [base],
      extraProviders: [
        {
          definition: { name: "custom_echo", kind: "read", risk: "low" },
          provider: {
            name: "custom_echo",
            execute: async () => ({ ok: true, output: "echo" }),
          },
        },
      ],
    })
    expect(registry.get("custom_echo")).toEqual({
      name: "custom_echo",
      kind: "read",
      risk: "low",
    })
    const gate = new PolicyGate(defaultPermissionPolicy("owner-1"), () => 1000)
    const def: ToolDefinition = {
      name: "custom_echo" as ToolDefinition["name"],
      risk: "low",
      run: vi.fn(async () => ({ ok: true, output: "unused" })),
    }
    const outcome = await executeToolThroughBoundary(
      registry,
      gate,
      def,
      {},
      { subject: "owner-1", resource: "conv-1", grant: null },
    )
    expect(outcome).toEqual({ ok: true, output: "echo" })
  })

  it("splits MCP tools and registers them as extra providers", () => {
    const core: ToolDefinition = {
      name: "get_current_time" as ToolDefinition["name"],
      risk: "low",
      run: vi.fn(async () => ({ ok: true, output: "now" })),
    }
    const mcp: ToolDefinition = {
      name: "mcp_search" as ToolDefinition["name"],
      risk: "high",
      run: vi.fn(async () => ({ ok: true, output: "found" })),
    }
    const split = splitCoreAndMcpTools([core, mcp])
    expect(split.core.map((t) => t.name)).toEqual(["get_current_time"])
    expect(split.mcp.map((t) => t.name)).toEqual(["mcp_search"])
    const registry = createProductionCapabilityRegistry({
      tools: split.core,
      extraProviders: mcpCapabilityProvidersFromTools(split.mcp, {}),
    })
    expect(registry.get("get_current_time")).toBeDefined()
    expect(registry.get("mcp_search")).toEqual({
      name: "mcp_search",
      kind: "command",
      risk: "high",
    })
  })

  it("persists a waiting-approval step when an Ask occurs with an approval context", async () => {
    const db = await makeTestDb()
    try {
      const store: RuntimeStore = createRuntimeStore(db.db)
      const createdAt = new Date("2026-08-20T00:00:00Z")
      const inbound = await store.createConversationWithUserMessage({
        conversationId: crypto.randomUUID(),
        messageId: crypto.randomUUID(),
        subject: "owner-1",
        content: { text: "run it" },
        triggerSource: "channel",
        idempotencyKey: crypto.randomUUID(),
        createdAt,
      })
      const run = await store.createRun({
        id: crypto.randomUUID(),
        conversationId: inbound.conversationId,
        parentRunId: null,
        triggerSource: "channel",
        idempotencyKey: crypto.randomUUID(),
        subject: "owner-1",
        goal: "run it",
        budget: {},
        deadline: null,
        createdAt,
      })
      await store.transitionRunStatus(run.id, run.version, "running", createdAt)

      const def: ToolDefinition = {
        name: "run_command" as ToolDefinition["name"],
        risk: "high",
        run: vi.fn(async () => ({ ok: true, output: "ok" })),
      }
      const registry = buildCapabilityRegistryFromTools([def])
      const gate = new PolicyGate(productionPermissionPolicy("owner-1"), () => 1000)
      const outcome = await executeToolThroughBoundary(
        registry,
        gate,
        def,
        { argv: ["pwd"] },
        { subject: "owner-1", resource: "pwd", grant: null },
        {
          store,
          runId: run.id,
          conversationId: run.conversationId,
          subject: "owner-1",
        },
      )
      expect(outcome.ok).toBe(false)
      if (!outcome.ok && "pendingApproval" in outcome) {
        expect(outcome.pendingApproval.stepId).toBeTruthy()
        const steps = await store.listWaitingApprovalSteps()
        expect(steps.some((s) => s.id === outcome.pendingApproval.stepId)).toBe(true)
      } else {
        throw new Error("expected pendingApproval envelope")
      }
      expect((await store.getRun(run.id))?.status).toBe("waiting_approval")
      expect(def.run).not.toHaveBeenCalled()
    } finally {
      await db.close()
    }
  })

  it("returns capability failed when an allowed tool errors", async () => {
    const def: ToolDefinition = {
      name: "get_current_time" as ToolDefinition["name"],
      risk: "low",
      run: vi.fn(async () => ({ ok: false, reason: "boom" })),
    }
    const registry = buildCapabilityRegistryFromTools([def])
    const gate = new PolicyGate(defaultPermissionPolicy("owner-1"), () => 1000)
    const outcome = await executeToolThroughBoundary(
      registry,
      gate,
      def,
      {},
      { subject: "owner-1", resource: "conv-1", grant: null },
    )
    expect(outcome).toEqual({ ok: false, reason: "boom" })
  })
})
