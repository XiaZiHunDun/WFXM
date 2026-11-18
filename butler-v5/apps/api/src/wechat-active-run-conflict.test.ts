import { describe, expect, it } from "vitest"
import { activeRunConflictReply } from "./wechat-inbound-butler.js"

// D58 T5 (audit #3 F-18): ActiveMainRunConflict reply used to leak the
// raw `status` token ("waiting_approval" / "waiting_external") into
// owner-facing text. Owner never sees those internal state names —
// surface them as friendly Chinese instead.
describe("activeRunConflictReply (D58 T5 owner-facing label)", () => {
  it("maps waiting_approval to '审批' wording, no literal token", () => {
    const reply = activeRunConflictReply("waiting_approval")
    expect(reply).not.toContain("waiting_approval")
    expect(reply).toContain("审批")
  })

  it("maps waiting_external to '外部' wording, no literal token", () => {
    const reply = activeRunConflictReply("waiting_external")
    expect(reply).not.toContain("waiting_external")
    expect(reply).toContain("外部")
  })

  it("keeps running/queued free of Run ids and internal tokens", () => {
    for (const status of ["running", "queued", "unknown-status"]) {
      const reply = activeRunConflictReply(status)
      expect(reply).not.toMatch(/run-[0-9a-f]|\bRun\b|waiting_/)
      expect(reply).toContain("未完成")
    }
  })
})
