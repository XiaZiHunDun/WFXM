import { describe, test, expect, vi } from "vitest"
import { evaluateInlineApproval, DEFAULT_COOLDOWN_MS } from "./policy"
import type { AuditLogReader, AuditEventSummary } from "./signal"

function readerWithCount(count: number, degraded = false): AuditLogReader {
  return {
    readRecent: vi.fn(async () => {
      if (degraded) {
        throw new Error("audit log reader degraded")
      }
      return Array.from({ length: count }, (_, i): AuditEventSummary => ({
        event_id: `e${i}`,
        tool_name: "read_file",
        actor: "owner",
        ts: Date.now() - i * 1000,
        decision: "allow",
      }))
    }),
  }
}

describe("evaluateInlineApproval", () => {
  test("F6: low-signal normal tool returns allow", async () => {
    const decision = await evaluateInlineApproval(
      { tool_name: "read_file", args: {} },
      readerWithCount(1),
    )
    expect(decision.action).toBe("allow")
  })

  test("F7: high-signal normal tool returns cooldown", async () => {
    const decision = await evaluateInlineApproval(
      { tool_name: "read_file", args: {} },
      readerWithCount(3),
    )
    if (decision.action !== "cooldown") throw new Error("expected cooldown")
    expect(decision.duration_ms).toBe(DEFAULT_COOLDOWN_MS)
    expect(decision.signal.count).toBe(3)
  })

  test("F8: high-sensitivity low-signal returns checklist", async () => {
    const decision = await evaluateInlineApproval(
      { tool_name: "send_email", args: {} },
      readerWithCount(0),
    )
    if (decision.action !== "checklist") throw new Error("expected checklist")
    expect(decision.items).toHaveLength(2)
  })

  test("F9: high-sensitivity high-signal returns cooldown (first round; caller re-evaluates)", async () => {
    const decision = await evaluateInlineApproval(
      { tool_name: "send_email", args: {} },
      readerWithCount(3),
    )
    if (decision.action !== "cooldown") throw new Error("expected cooldown")
    expect(decision.duration_ms).toBe(DEFAULT_COOLDOWN_MS)
  })

  test("F10: degraded signal always returns allow", async () => {
    const decision = await evaluateInlineApproval(
      { tool_name: "send_email", args: {} },
      readerWithCount(0, true),
    )
    expect(decision.action).toBe("allow")
  })
})

describe("DEFAULT_COOLDOWN_MS", () => {
  test("default cooldown is 3000ms", () => {
    expect(DEFAULT_COOLDOWN_MS).toBe(3000)
  })
})
