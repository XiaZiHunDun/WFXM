import { describe, expect, it } from "vitest"
import {
  assertOwnerApprovalRunTrigger,
  buildOwnerApprovalRunTrigger,
} from "./owner-approval-trigger.js"

describe("owner approval RunTrigger", () => {
  it("builds an api trigger for approval resume", () => {
    const trigger = buildOwnerApprovalRunTrigger({
      subject: "owner-1",
      conversationId: "conv-1",
      stepId: "step-1",
      capability: "get_current_time",
    })
    expect(trigger.source).toBe("api")
    expect(trigger.trustLevel).toBe("owner")
    expect(trigger.idempotencyKey).toBe("owner-approve-step-1")
    expect(assertOwnerApprovalRunTrigger(trigger)).toEqual({ ok: true })
  })
})
