import { describe, expect, it, vi } from "vitest"
import { runTool, type ToolDefinition } from "./tool-runtime.js"

describe("runTool", () => {
  it("returns the handler output on success", async () => {
    const def: ToolDefinition = {
      name: "echo" as ToolDefinition["name"],
      risk: "low",
      run: vi.fn(async (args: Record<string, unknown>) => ({ ok: true, output: args })),
    }
    const r = await runTool(def, { x: 1 }, { timeoutMs: 1000 })
    expect(r.ok).toBe(true)
    if (r.ok) expect(r.output).toEqual({ x: 1 })
  })

  it("times out a slow handler", async () => {
    const slow: ToolDefinition = {
      name: "slow" as ToolDefinition["name"],
      risk: "low",
      run: () =>
        new Promise<{ ok: true; output: unknown }>((r) =>
          setTimeout(() => r({ ok: true, output: "done" }), 5000),
        ),
    }
    const r = await runTool(slow, {}, { timeoutMs: 50 })
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.reason).toMatch(/timeout/i)
  })

  it("catches handler throw and returns failure", async () => {
    const broken: ToolDefinition = {
      name: "broken" as ToolDefinition["name"],
      risk: "low",
      run: async () => {
        throw new Error("downstream-down")
      },
    }
    const r = await runTool(broken, {}, { timeoutMs: 1000 })
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.reason).toBe("downstream-down")
  })

  it("aborts handler via AbortSignal", async () => {
    const ctrl = new AbortController()
    const slow: ToolDefinition = {
      name: "slow" as ToolDefinition["name"],
      risk: "low",
      run: (_args, signal) =>
        new Promise((resolve, reject) => {
          signal?.addEventListener("abort", () => reject(new Error("aborted")))
          setTimeout(() => resolve({ ok: true, output: "ran" }), 5000)
        }),
    }
    const r = runTool(slow, {}, { timeoutMs: 5000, signal: ctrl.signal })
    setTimeout(() => ctrl.abort(), 30)
    const r2 = await r
    expect(r2.ok).toBe(false)
    if (!r2.ok) expect(r2.reason).toBe("aborted")
  })
})
