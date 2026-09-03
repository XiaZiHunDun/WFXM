import { describe, it, expect } from "vitest"
import {
  workflowTransition,
  startWorkflow,
  pendingWorkflow,
  advanceStep,
  waitForApproval,
  failWorkflow,
} from "./transitions.js"
import type {
  WorkflowState,
  WorkflowEvent,
  WorkflowId,
  WorkflowStep,
  WorkflowStepId,
} from "./types.js"

const wid = "wf-1" as unknown as WorkflowId

describe("workflows/transitions", () => {
  describe("NotStarted → Running", () => {
    it("WorkflowStarted transitions to Running", () => {
      const state: WorkflowState = { _tag: "NotStarted" }
      const event: WorkflowEvent = { _tag: "WorkflowStarted", workflowId: wid }
      const result = workflowTransition(state, event)
      expect(result._tag).toBe("Running")
      if (result._tag === "Running") {
        expect(result.channels).toEqual([])
      }
    })

    it("WorkflowStarted from non-NotStarted is a no-op", () => {
      const state: WorkflowState = { _tag: "Running", channels: [] }
      const event: WorkflowEvent = { _tag: "WorkflowStarted", workflowId: wid }
      const result = workflowTransition(state, event)
      expect(result).toBe(state)
    })
  })

  describe("Channel management", () => {
    it("ChannelCreated adds a channel to Running state", () => {
      const state: WorkflowState = { _tag: "Running", channels: [] }
      const event: WorkflowEvent = { _tag: "ChannelCreated", channelId: "ch-1" }
      const result = workflowTransition(state, event)
      expect(result._tag).toBe("Running")
      if (result._tag === "Running") {
        expect(result.channels).toHaveLength(1)
        expect(result.channels[0]?.id).toBe("ch-1")
        expect(result.channels[0]?.suspended).toBe(false)
      }
    })

    it("ChannelCreated appends to existing channels", () => {
      const state: WorkflowState = {
        _tag: "Running",
        channels: [{ id: "ch-1", state: null, suspended: false }],
      }
      const event: WorkflowEvent = { _tag: "ChannelCreated", channelId: "ch-2" }
      const result = workflowTransition(state, event)
      expect(result._tag).toBe("Running")
      if (result._tag === "Running") {
        expect(result.channels).toHaveLength(2)
      }
    })

    it("ChannelCreated from non-Running is a no-op", () => {
      const state: WorkflowState = { _tag: "NotStarted" }
      const event: WorkflowEvent = { _tag: "ChannelCreated", channelId: "ch-1" }
      expect(workflowTransition(state, event)._tag).toBe("NotStarted")
    })

    it("ChannelCompleted updates matching channel state", () => {
      const state: WorkflowState = {
        _tag: "Running",
        channels: [{ id: "ch-1", state: null, suspended: false }],
      }
      const event: WorkflowEvent = {
        _tag: "ChannelCompleted",
        channelId: "ch-1",
        result: { ok: true },
      }
      const result = workflowTransition(state, event)
      expect(result._tag).toBe("Running")
      if (result._tag === "Running") {
        expect(result.channels[0]?.state).toEqual({ ok: true })
      }
    })

    it("ChannelCompleted non-matching channelId is a no-op", () => {
      const state: WorkflowState = {
        _tag: "Running",
        channels: [{ id: "ch-1", state: null, suspended: false }],
      }
      const event: WorkflowEvent = {
        _tag: "ChannelCompleted",
        channelId: "ch-2",
        result: { ok: true },
      }
      const result = workflowTransition(state, event)
      if (result._tag === "Running") {
        expect(result.channels[0]?.state).toBeNull()
      }
    })
  })

  describe("Merge and completion", () => {
    it("ChannelsMerged transitions to AwaitingMerge", () => {
      const state: WorkflowState = { _tag: "Running", channels: [] }
      const event: WorkflowEvent = {
        _tag: "ChannelsMerged",
        results: [1, 2, 3],
      }
      const result = workflowTransition(state, event)
      expect(result._tag).toBe("AwaitingMerge")
      if (result._tag === "AwaitingMerge") {
        expect(result.results).toEqual([1, 2, 3])
      }
    })

    it("WorkflowCompleted transitions to Completed", () => {
      const state: WorkflowState = { _tag: "AwaitingMerge", results: [] }
      const event: WorkflowEvent = {
        _tag: "WorkflowCompleted",
        outputs: [{ file: "a.ts" }],
      }
      const result = workflowTransition(state, event)
      expect(result._tag).toBe("Completed")
      if (result._tag === "Completed") {
        expect(result.outputs).toEqual([{ file: "a.ts" }])
      }
    })

    it("WorkflowFailed transitions to Failed", () => {
      const state: WorkflowState = { _tag: "Running", channels: [] }
      const event: WorkflowEvent = {
        _tag: "WorkflowFailed",
        error: { _tag: "LLMUnavailable", provider: "test" },
      }
      const result = workflowTransition(state, event)
      expect(result._tag).toBe("Failed")
      if (result._tag === "Failed") {
        expect(result.error._tag).toBe("LLMUnavailable")
      }
    })
  })

  describe("default: unknown event", () => {
    it("returns same state for unknown event", () => {
      const state: WorkflowState = { _tag: "NotStarted" }
      // @ts-expect-error testing invalid event
      const result = workflowTransition(state, { _tag: "UnknownEvent" })
      expect(result).toBe(state)
    })
  })

  // ─── R2.2 ─────────────────────────────────────────────
  describe("workflow lifecycle (R2.2)", () => {
    const steps: WorkflowStep[] = [
      {
        id: "s1" as WorkflowStepId,
        kind: "tool",
        spec: {
          executable: "echo",
          args: ["hi"],
          cwd: "/",
          timeoutMs: 1000,
          network: "none",
        },
      },
      { id: "s2" as WorkflowStepId, kind: "approval", approver: "owner" },
    ]

    it("starts a workflow with steps", () => {
      const w = startWorkflow(wid, steps)
      expect(w.status).toBe("pending")
      expect(w.steps).toBe(steps)
      expect(w.currentStepId).toBeNull()
      expect(w.error).toBeNull()
    })

    it("starts a workflow with empty steps (no-throw)", () => {
      const w = startWorkflow(wid, [])
      expect(w.status).toBe("pending")
      expect(w.error).toContain("至少需要")
    })

    it("advances a step", () => {
      let w = startWorkflow(wid, steps)
      w = pendingWorkflow(w)
      w = advanceStep(w, "s1" as WorkflowStepId)
      expect(w.currentStepId).toBe("s2")
      expect(w.status).toBe("running")
    })

    it("completes when last step advances", () => {
      let w = startWorkflow(wid, steps)
      w = pendingWorkflow(w)
      w = advanceStep(w, "s1" as WorkflowStepId)
      w = advanceStep(w, "s2" as WorkflowStepId)
      expect(w.status).toBe("completed")
      expect(w.currentStepId).toBeNull()
    })

    it("pauses for approval", () => {
      let w = startWorkflow(wid, steps)
      w = pendingWorkflow(w)
      w = waitForApproval(w, "s2" as WorkflowStepId, "owner")
      expect(w.status).toBe("waiting_approval")
      expect(w.currentStepId).toBe("s2")
    })

    it("fails the workflow", () => {
      let w = startWorkflow(wid, steps)
      w = failWorkflow(w, "boom")
      expect(w.status).toBe("failed")
      expect(w.error).toBe("boom")
    })

    it("rejects unknown step on advance (no-throw)", () => {
      let w = startWorkflow(wid, steps)
      w = pendingWorkflow(w)
      w = advanceStep(w, "missing" as WorkflowStepId)
      expect(w.error).toContain("step not found")
    })
  })
})
