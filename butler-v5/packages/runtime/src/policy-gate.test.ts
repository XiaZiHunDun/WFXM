import { describe, expect, it, vi } from "vitest"
import {
  actionRequestFromTool,
  CapabilityRegistry,
  defaultPermissionPolicy,
  PolicyGate,
  readKillSwitch,
  SIDE_EFFECT_KINDS,
  type CapabilityDefinition,
  type CapabilityProvider,
} from "./policy-gate.js"

describe("CapabilityRegistry P3-2 register/unregister", () => {
  const definition: CapabilityDefinition = {
    name: "read_file",
    kind: "read",
    risk: "low",
    declared: {
      inputSchema: { path: "string" },
      outputSchema: { text: "string" },
      sandboxProfile: "workspace-read",
      timeoutMs: 3000,
      idempotent: true,
      auditPolicy: "summary",
    },
  }
  const provider: CapabilityProvider = {
    name: "read_file",
    execute: async () => ({ ok: true, output: "x" }),
  }

  it("surfaces declared metadata and isRegistered", () => {
    const registry = new CapabilityRegistry()
    registry.register(definition, provider)
    expect(registry.isRegistered("read_file")).toBe(true)
    expect(registry.declared("read_file")).toEqual({
      inputSchema: { path: "string" },
      outputSchema: { text: "string" },
      sandboxProfile: "workspace-read",
      timeoutMs: 3000,
      idempotent: true,
      auditPolicy: "summary",
    })
    expect(registry.declared("nope")).toBeUndefined()
  })

  it("unregisters a capability and drops execution to Blocked/unknown", async () => {
    const gate = new PolicyGate(defaultPermissionPolicy("owner-1"), () => 1000)
    const registry = new CapabilityRegistry()
    registry.register(definition, provider)
    expect(registry.unregister("read_file")).toBe(true)
    expect(registry.unregister("read_file")).toBe(false)
    expect(registry.isRegistered("read_file")).toBe(false)
    const request = actionRequestFromTool(
      "read_file",
      "owner-1",
      "README.md",
      {},
      { name: "read_file", kind: "read", risk: "low" },
    )
    const outcome = await registry.executeThroughBoundary(gate, request, {}, null)
    expect(outcome._tag).toBe("Blocked")
  })
})

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

describe("BUTLER_V5_KILL_SWITCH", () => {
  it("parses kill switch env truthiness", () => {
    expect(readKillSwitch({})).toBe(false)
    expect(readKillSwitch({ BUTLER_V5_KILL_SWITCH: "0" })).toBe(false)
    expect(readKillSwitch({ BUTLER_V5_KILL_SWITCH: "off" })).toBe(false)
    expect(readKillSwitch({ BUTLER_V5_KILL_SWITCH: "1" })).toBe(true)
    expect(readKillSwitch({ BUTLER_V5_KILL_SWITCH: "true" })).toBe(true)
    expect(readKillSwitch({ BUTLER_V5_KILL_SWITCH: "YES" })).toBe(true)
  })

  it("hard-stops side effects even with a valid grant (fail-closed)", () => {
    const gate = new PolicyGate(defaultPermissionPolicy("owner-1"), () => 1000, {
      killSwitch: true,
    })
    const command = actionRequestFromTool(
      "run_command",
      "owner-1",
      "pwd",
      { argv: ["pwd"] },
      { name: "run_command", kind: "command", risk: "high" },
    )
    const decision = gate.evaluate(command, {
      id: "g",
      runId: "r",
      subject: "owner-1",
      scope: { capabilities: ["run_command"] },
      remainingUses: 1,
      expiresAtMs: 9999,
      createdAtMs: 0,
      delegable: false,
      approvalId: null,
      sandboxProfile: null,
      networkAllowlist: null,
    })
    expect(decision).toEqual({
      _tag: "Deny",
      reason: "global kill switch is active (BUTLER_V5_KILL_SWITCH)",
    })
  })

  it("still allows read-only capabilities under kill switch", () => {
    const gate = new PolicyGate(defaultPermissionPolicy("owner-1"), () => 1000, {
      killSwitch: true,
    })
    const readRequest = actionRequestFromTool(
      "read_file",
      "owner-1",
      "README.md",
      { path: "README.md" },
      { name: "read_file", kind: "read", risk: "low" },
    )
    expect(gate.evaluate(readRequest, null)._tag).toBe("Allow")
  })

  it("SIDE_EFFECT_KINDS excludes read/model", () => {
    expect(SIDE_EFFECT_KINDS).toEqual(["write", "command", "outbound", "delegate"])
  })
})
