import { describe, expect, it, vi } from "vitest"
import {
  actionRequestFromTool,
  CapabilityRegistry,
  defaultPermissionPolicy,
  PolicyGate,
  type CapabilityDefinition,
  type CapabilityProvider,
} from "./policy-gate.js"

describe("PolicyGate and CapabilityRegistry", () => {
  it("blocks unknown capabilities at the provider boundary", async () => {
    const gate = new PolicyGate(defaultPermissionPolicy("owner-1"), () => 1000)
    const registry = new CapabilityRegistry()
    const request = actionRequestFromTool(
      "missing_tool",
      "owner-1",
      "x",
      {},
      { name: "missing_tool", kind: "read", risk: "low" },
    )
    const outcome = await registry.executeThroughBoundary(gate, request, {}, null)
    expect(outcome._tag).toBe("Blocked")
  })

  it("executes allowed capabilities through the boundary", async () => {
    const gate = new PolicyGate(defaultPermissionPolicy("owner-1"), () => 1000)
    const registry = new CapabilityRegistry()
    const definition: CapabilityDefinition = {
      name: "read_file",
      kind: "read",
      risk: "low",
    }
    const provider: CapabilityProvider = {
      name: "read_file",
      execute: vi.fn(async () => ({ ok: true, output: "hello" })),
    }
    registry.register(definition, provider)
    const request = actionRequestFromTool("read_file", "owner-1", "README.md", {}, definition)
    const outcome = await registry.executeThroughBoundary(gate, request, {}, null)
    expect(outcome).toEqual({
      _tag: "Executed",
      result: { ok: true, output: "hello" },
    })
  })
})
