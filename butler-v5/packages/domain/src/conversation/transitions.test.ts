import { describe, it, expect } from "vitest"
import { applyToolResult, openTurn, submitUserMessage, transition } from "./transitions.js"
import type {
  ConversationId,
  ConversationState,
  ConversationEvent,
  LoopId,
  Conversation,
  ToolCallId,
} from "./types.js"

const cid = "conv-1" as unknown as ConversationId
const lid = "loop-1" as unknown as LoopId

describe("conversation/transitions", () => {
  describe("Idle → Running", () => {
    it("ConversationStarted transitions to Running", () => {
      const state: ConversationState = { _tag: "Idle" }
      const event: ConversationEvent = {
        _tag: "ConversationStarted",
        conversationId: cid,
      }
      const result = transition(state, event)
      expect(result._tag).toBe("Running")
    })

    it("ConversationStarted from non-Idle state is a no-op", () => {
      const state: ConversationState = { _tag: "Running", loopId: lid }
      const event: ConversationEvent = {
        _tag: "ConversationStarted",
        conversationId: cid,
      }
      const result = transition(state, event)
      expect(result).toBe(state)
    })
  })

  describe("MessageAdded", () => {
    it("does not change state", () => {
      const state: ConversationState = { _tag: "Running", loopId: lid }
      const event: ConversationEvent = {
        _tag: "MessageAdded",
        message: {
          id: "msg-1",
          conversationId: cid,
          role: "user",
          content: "hello",
          createdAt: Date.now(),
        },
      }
      const result = transition(state, event)
      expect(result).toBe(state)
    })
  })

  describe("ToolCallStarted / ToolCallCompleted", () => {
    it("ToolCallStarted from Running → AwaitingToolResult", () => {
      const state: ConversationState = { _tag: "Running", loopId: lid }
      const event: ConversationEvent = {
        _tag: "ToolCallStarted",
        toolCallId: "tc-1",
      }
      const result = transition(state, event)
      expect(result._tag).toBe("AwaitingToolResult")
      if (result._tag === "AwaitingToolResult") {
        expect(result.toolCallId).toBe("tc-1")
        expect(result.loopId).toBe(lid)
      }
    })

    it("ToolCallStarted from non-Running is a no-op", () => {
      const state: ConversationState = { _tag: "Idle" }
      const event: ConversationEvent = {
        _tag: "ToolCallStarted",
        toolCallId: "tc-1",
      }
      const result = transition(state, event)
      expect(result._tag).toBe("Idle")
    })

    it("ToolCallCompleted matching toolCallId → Running", () => {
      const state: ConversationState = {
        _tag: "AwaitingToolResult",
        toolCallId: "tc-1",
        loopId: lid,
      }
      const event: ConversationEvent = {
        _tag: "ToolCallCompleted",
        toolCallId: "tc-1",
        result: { ok: true },
      }
      const result = transition(state, event)
      expect(result._tag).toBe("Running")
      if (result._tag === "Running") {
        expect(result.loopId).toBe(lid)
      }
    })

    it("ToolCallCompleted with non-matching toolCallId is a no-op", () => {
      const state: ConversationState = {
        _tag: "AwaitingToolResult",
        toolCallId: "tc-1",
        loopId: lid,
      }
      const event: ConversationEvent = {
        _tag: "ToolCallCompleted",
        toolCallId: "tc-2",
        result: { ok: true },
      }
      const result = transition(state, event)
      expect(result._tag).toBe("AwaitingToolResult")
    })
  })

  describe("OwnerInput received / timeout", () => {
    it("OwnerInputReceived → Running", () => {
      const state: ConversationState = {
        _tag: "AwaitingOwnerInput",
        prompt: "approve?",
        since: Date.now(),
      }
      const event: ConversationEvent = {
        _tag: "OwnerInputReceived",
        loopId: lid,
      }
      const result = transition(state, event)
      expect(result._tag).toBe("Running")
      if (result._tag === "Running") {
        expect(result.loopId).toBe(lid)
      }
    })

    it("OwnerInputTimeout → Failed with GuardRejected", () => {
      const state: ConversationState = {
        _tag: "AwaitingOwnerInput",
        prompt: "approve?",
        since: Date.now(),
      }
      const event: ConversationEvent = { _tag: "OwnerInputTimeout" }
      const result = transition(state, event)
      expect(result._tag).toBe("Failed")
      if (result._tag === "Failed") {
        expect(result.error._tag).toBe("GuardRejected")
        if (result.error._tag === "GuardRejected") {
          expect(result.error.reason._tag).toBe("OwnerOffline")
        }
      }
    })

    it("OwnerInputReceived from non-AwaitingOwnerInput is a no-op", () => {
      const state: ConversationState = { _tag: "Idle" }
      const event: ConversationEvent = {
        _tag: "OwnerInputReceived",
        loopId: lid,
      }
      const result = transition(state, event)
      expect(result._tag).toBe("Idle")
    })
  })

  describe("Review flow", () => {
    it("ReviewRequested from Running → AwaitingReview", () => {
      const state: ConversationState = { _tag: "Running", loopId: lid }
      const event: ConversationEvent = {
        _tag: "ReviewRequested",
        receiptId: "r-1",
        reviewerAgent: "claude-3-5-haiku",
      }
      const result = transition(state, event)
      expect(result._tag).toBe("AwaitingReview")
      if (result._tag === "AwaitingReview") {
        expect(result.receiptId).toBe("r-1")
        expect(result.reviewerAgent).toBe("claude-3-5-haiku")
      }
    })

    it("ReviewCompleted with approval → Running", () => {
      const state: ConversationState = {
        _tag: "AwaitingReview",
        receiptId: "r-1",
        reviewerAgent: "reviewer",
      }
      const event: ConversationEvent = {
        _tag: "ReviewCompleted",
        receiptId: "r-1",
        approved: true,
      }
      const result = transition(state, event)
      expect(result._tag).toBe("Running")
    })

    it("ReviewCompleted with rejection → Failed", () => {
      const state: ConversationState = {
        _tag: "AwaitingReview",
        receiptId: "r-1",
        reviewerAgent: "reviewer",
      }
      const event: ConversationEvent = {
        _tag: "ReviewCompleted",
        receiptId: "r-1",
        approved: false,
      }
      const result = transition(state, event)
      expect(result._tag).toBe("Failed")
    })
  })

  describe("ConversationCompleted / Failed", () => {
    it("ConversationCompleted → Completed", () => {
      const state: ConversationState = { _tag: "Running", loopId: lid }
      const event: ConversationEvent = {
        _tag: "ConversationCompleted",
        receipt: undefined,
      }
      const result = transition(state, event)
      expect(result._tag).toBe("Completed")
    })

    it("ConversationCompleted with receipt", () => {
      const state: ConversationState = { _tag: "Running", loopId: lid }
      const receipt = {
        id: "r-1",
        intent: "test",
        evidenceFiles: [],
        locDelta: { added: 0, removed: 0 },
        chainCompleteness: 1,
        guardFindings: [],
        authorAgent: "test",
        createdAt: 1,
      }
      const event: ConversationEvent = {
        _tag: "ConversationCompleted",
        receipt,
      }
      const result = transition(state, event)
      expect(result._tag).toBe("Completed")
      if (result._tag === "Completed") {
        expect(result.receipt).toBe(receipt)
      }
    })

    it("ConversationFailed → Failed", () => {
      const state: ConversationState = { _tag: "Running", loopId: lid }
      const event: ConversationEvent = {
        _tag: "ConversationFailed",
        error: { _tag: "LLMUnavailable", provider: "test" },
      }
      const result = transition(state, event)
      expect(result._tag).toBe("Failed")
      if (result._tag === "Failed") {
        expect(result.error._tag).toBe("LLMUnavailable")
      }
    })
  })

  describe("default: unknown event", () => {
    it("returns same state for unknown event", () => {
      const state: ConversationState = { _tag: "Idle" }
      // @ts-expect-error testing invalid event
      const result = transition(state, { _tag: "UnknownEvent" })
      expect(result).toBe(state)
    })
  })
})

describe("conversation transitions", () => {
  const empty: Conversation = {
    id: "conv-1" as unknown as ConversationId,
    projectId: "proj-1" as unknown as Conversation["projectId"],
    status: "open",
    turns: [],
  }

  it("opens a turn on user message", () => {
    const c = submitUserMessage(empty, "hello")
    expect(c.turns.length).toBe(1)
    expect(c.turns[0]?.status).toBe("running")
  })

  it("applies a successful tool result", () => {
    const c0 = submitUserMessage(empty, "hi")
    const c1 = openTurn(c0, { toolCallId: "tc-1" as unknown as ToolCallId })
    const c2 = applyToolResult(c1, { toolCallId: "tc-1" as unknown as ToolCallId, output: "ok" })
    expect(c2.turns[0]?.status).toBe("tooled")
  })
})
