import { describe, expect, it } from "vitest"
import { canTransitionRun, transitionRun, type Run, type RunStatus } from "./index.js"

const baseRun: Run = {
  id: "run-1",
  conversationId: "conversation-1",
  parentRunId: null,
  trigger: {
    subject: "owner-1",
    source: "channel",
    conversationRef: "conversation-1",
    payload: { text: "hello" },
    trustLevel: "trusted",
    idempotencyKey: "inbound-1",
  },
  goal: "reply",
  budget: { maxSteps: 5 },
  deadline: null,
  status: "queued",
  version: 1,
  createdAt: 1,
  updatedAt: 1,
}

describe("runtime Run transitions", () => {
  it("accepts every transition in the target state machine", () => {
    const legal: readonly [RunStatus, RunStatus][] = [
      ["queued", "running"],
      ["running", "waiting_approval"],
      ["waiting_approval", "running"],
      ["waiting_approval", "failed"],
      ["waiting_approval", "cancelled"],
      ["waiting_approval", "expired"],
      ["running", "waiting_external"],
      ["waiting_external", "running"],
      ["waiting_external", "cancelled"],
      ["waiting_external", "expired"],
      ["queued", "cancelled"],
      ["queued", "expired"],
      ["running", "succeeded"],
      ["running", "failed"],
      ["running", "cancelled"],
      ["running", "expired"],
    ]

    for (const [from, to] of legal) {
      expect(canTransitionRun(from, to), `${from} -> ${to}`).toBe(true)
    }
  })

  it("rejects transitions out of terminal states", () => {
    for (const terminal of ["succeeded", "failed", "cancelled", "expired"] as const) {
      expect(canTransitionRun(terminal, "running")).toBe(false)
    }
  })

  it("returns a new versioned Run for a legal transition", () => {
    const result = transitionRun(baseRun, "running", 2)

    expect(result).toEqual({
      _tag: "TransitionAccepted",
      run: { ...baseRun, status: "running", version: 2, updatedAt: 2 },
    })
  })

  it("preserves the Run when a transition is illegal", () => {
    const result = transitionRun(baseRun, "succeeded", 2)

    expect(result).toEqual({
      _tag: "TransitionRejected",
      run: baseRun,
      from: "queued",
      to: "succeeded",
    })
  })
})
