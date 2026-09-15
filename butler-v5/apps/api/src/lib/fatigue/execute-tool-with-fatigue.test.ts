import { describe, test, expect, vi } from "vitest"
import { executeToolWithFatigue } from "./execute-tool-with-fatigue"
import type { AuditLogReader, AuditEventSummary } from "./signal"

function makeReader(count: number): AuditLogReader {
  return {
    readRecent: vi.fn(async (): Promise<readonly AuditEventSummary[]> =>
      Array.from({ length: count }, (_, i): AuditEventSummary => ({
        event_id: `e${i}`,
        tool_name: "read_file",
        actor: "owner",
        ts: Date.now() - i * 1000,
        decision: "allow",
      }))
    ),
  }
}

describe("executeToolWithFatigue", () => {
  test("F1: low-signal normal tool returns allow", async () => {
    const result = await executeToolWithFatigue("read_file", {}, makeReader(0))
    expect(result.kind).toBe("allow")
  })

  test("F2: high-signal normal tool returns cooldown with durationMs", async () => {
    const result = await executeToolWithFatigue("read_file", {}, makeReader(3))
    expect(result.kind).toBe("cooldown")
    if (result.kind !== "cooldown") throw new Error("expected cooldown")
    expect(result.durationMs).toBe(3000)
  })

  test("F3: high-sensitivity tool returns checklist with items", async () => {
    const result = await executeToolWithFatigue("send_email", {}, makeReader(0))
    expect(result.kind).toBe("checklist")
    if (result.kind !== "checklist") throw new Error("expected checklist")
    expect(result.items.length).toBeGreaterThan(0)
  })
})
