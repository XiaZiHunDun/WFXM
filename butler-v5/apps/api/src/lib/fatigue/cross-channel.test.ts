import { describe, test, expect, vi } from "vitest"
import { evaluateChannelApproval } from "./inline-approval-wiring"
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

describe("cross-channel approval wiring", () => {
  test("X1: wechat high-signal send_email produces cooldown (first round)", async () => {
    const result = await evaluateChannelApproval(
      "send_email",
      { to: "x@y.com" },
      makeReader(3),
      { channel: "wechat", actor: "owner", correlationId: "c1" },
    )
    expect(result.decision.action).toBe("cooldown")
    if (result.decision.action !== "cooldown") throw new Error("expected cooldown")
    expect(result.renderPrompt()).toContain("已批 3 个")
    expect(result.renderPrompt()).toContain("稍等 3s")
  })

  test("X2: telegram high-signal delete_file produces cooldown (first round)", async () => {
    const result = await evaluateChannelApproval(
      "delete_file",
      { path: "/tmp/x" },
      makeReader(3),
      { channel: "telegram", actor: "owner", correlationId: "c2" },
    )
    expect(result.decision.action).toBe("cooldown")
  })

  test("X3: CLI high-signal normal tool produces cooldown", async () => {
    const result = await evaluateChannelApproval(
      "read_file",
      { path: "/tmp/x" },
      makeReader(3),
      { channel: "cli", actor: "owner", correlationId: "c3" },
    )
    expect(result.decision.action).toBe("cooldown")
    if (result.decision.action !== "cooldown") throw new Error("expected cooldown")
    expect(result.decision.duration_ms).toBe(3000)
  })
})
