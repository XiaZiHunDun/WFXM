import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { Effect } from "effect"
import type { LLMAdapter, LLMMessage } from "@butler/adapters"
import { EventBridge } from "@butler/runtime/bridge.js"
import { makeTestDb } from "@butler/persistence/testing.js"
import { makeWiring, type Wiring } from "./wiring.js"
import { runButlerLoop, type ButlerLoopLogger } from "./wechat-inbound-butler.js"

function makeMockAdapter(replies: readonly LLMMessage[]): LLMAdapter {
  let i = 0
  return {
    complete: vi.fn((_messages, _opts) =>
      Effect.succeed(replies[i++] ?? { role: "assistant", content: "" }),
    ),
  }
}

describe("runButlerLoop", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let bridge: EventBridge
  let wiring: Wiring
  const silentLogger: ButlerLoopLogger = {
    warn: () => undefined,
    error: () => undefined,
  }

  beforeEach(async () => {
    db = await makeTestDb()
    bridge = new EventBridge({ db: db.db, workerId: "w-butler" })
    wiring = makeWiring({ bridge, adapters: {} as never, workerId: "w-butler" })
  })

  afterEach(async () => {
    await db.close()
    vi.restoreAllMocks()
  })

  it("returns stub when no LLM is configured and no adapter is injected", async () => {
    const result = await runButlerLoop({
      wiring,
      conversationId: "c-test-1",
      content: "hello",
      fromUserId: "u-1",
      projectId: "p-1",
      env: {},
      logger: silentLogger,
    })
    expect(result.reply).toContain("MVP stub reply")
    expect(result.finalDecision).toBe("Finish")
    expect(result.toolCalls).toBe(0)
  })

  it("returns Respond content when the model emits a Respond decision", async () => {
    const adapter = makeMockAdapter([
      { role: "assistant", content: JSON.stringify({ _tag: "Respond", content: "hi back" }) },
    ])
    const result = await runButlerLoop({
      wiring,
      conversationId: "c-test-2",
      content: "hello",
      fromUserId: "u-1",
      projectId: "p-1",
      env: {},
      logger: silentLogger,
      adapter,
    })
    expect(result.reply).toBe("hi back")
    expect(result.finalDecision).toBe("Respond")
    expect(result.iterations).toBe(1)
    expect(result.toolCalls).toBe(0)
  })

  it("treats plain text as Respond when decodeDecision fails", async () => {
    const adapter = makeMockAdapter([{ role: "assistant", content: "plain text reply" }])
    const result = await runButlerLoop({
      wiring,
      conversationId: "c-test-3",
      content: "hello",
      fromUserId: "u-1",
      projectId: "p-1",
      env: {},
      logger: silentLogger,
      adapter,
    })
    expect(result.reply).toBe("plain text reply")
    expect(result.finalDecision).toBe("Respond")
  })

  it("executes a tool and returns the model's follow-up Respond", async () => {
    const adapter = makeMockAdapter([
      {
        role: "assistant",
        content: JSON.stringify({
          _tag: "CallTool",
          toolName: "get_current_time",
          args: {},
        }),
      },
      {
        role: "assistant",
        content: JSON.stringify({ _tag: "Respond", content: "now is the time" }),
      },
    ])
    const result = await runButlerLoop({
      wiring,
      conversationId: "c-test-4",
      content: "what time is it?",
      fromUserId: "u-1",
      projectId: "p-1",
      env: {},
      logger: silentLogger,
      adapter,
    })
    expect(result.reply).toBe("now is the time")
    expect(result.finalDecision).toBe("Respond")
    expect(result.toolCalls).toBe(1)
    expect(result.iterations).toBe(2)
    expect(result.traces.some((t) => t.startsWith("get_current_time@"))).toBe(true)
  })

  it("executes recall_history with limit and feeds result back", async () => {
    // Pre-seed the event_store so recall_history has something to return.
    await bridge.appendConversationEvent({
      streamId: "c-test-5",
      eventId: "evt-prev-1",
      eventType: "ConversationStarted",
      correlationId: "corr-prev",
      actor: { kind: "system", id: "test" },
      event: { _tag: "ConversationStarted", projectId: "p-1", content: "earlier msg" },
    })
    const adapter = makeMockAdapter([
      {
        role: "assistant",
        content: JSON.stringify({
          _tag: "CallTool",
          toolName: "recall_history",
          args: { limit: 3 },
        }),
      },
      {
        role: "assistant",
        content: JSON.stringify({ _tag: "Respond", content: "I recall earlier msg" }),
      },
    ])
    const result = await runButlerLoop({
      wiring,
      conversationId: "c-test-5",
      content: "what did we talk about?",
      fromUserId: "u-1",
      projectId: "p-1",
      env: {},
      logger: silentLogger,
      adapter,
    })
    expect(result.reply).toBe("I recall earlier msg")
    expect(result.toolCalls).toBe(1)
    expect(result.traces.some((t) => t.includes("earlier msg"))).toBe(true)
  })

  it("falls back to stub on Finish decision", async () => {
    const adapter = makeMockAdapter([
      { role: "assistant", content: JSON.stringify({ _tag: "Finish", reason: "all done" }) },
    ])
    const result = await runButlerLoop({
      wiring,
      conversationId: "c-test-6",
      content: "hi",
      fromUserId: "u-1",
      projectId: "p-1",
      env: {},
      logger: silentLogger,
      adapter,
    })
    expect(result.reply).toContain("MVP stub reply")
    expect(result.finalDecision).toBe("Finish")
  })

  it("echoes AskApproval question back as reply", async () => {
    const adapter = makeMockAdapter([
      {
        role: "assistant",
        content: JSON.stringify({ _tag: "AskApproval", question: "delete?" }),
      },
    ])
    const result = await runButlerLoop({
      wiring,
      conversationId: "c-test-7",
      content: "delete the file",
      fromUserId: "u-1",
      projectId: "p-1",
      env: {},
      logger: silentLogger,
      adapter,
    })
    expect(result.reply).toContain("delete?")
    expect(result.reply).toContain("需要确认")
    expect(result.finalDecision).toBe("AskApproval")
  })

  it("falls back to stub when LLM call fails", async () => {
    const failingAdapter: LLMAdapter = {
      complete: vi.fn(() => Effect.fail(new Error("network-down"))),
    }
    const result = await runButlerLoop({
      wiring,
      conversationId: "c-test-8",
      content: "hi",
      fromUserId: "u-1",
      projectId: "p-1",
      env: {},
      logger: silentLogger,
      adapter: failingAdapter,
    })
    expect(result.reply).toContain("MVP stub reply")
    expect(result.finalDecision).toBe("Finish")
    expect(result.traces.some((t) => t.includes("llm failure"))).toBe(true)
  })

  it("bounds the loop at MAX_LOOP_ITERATIONS and falls back to stub", async () => {
    // Adapter always asks for a tool call — should hit the iteration cap.
    const adapter = makeMockAdapter(
      Array.from({ length: 10 }, () => ({
        role: "assistant" as const,
        content: JSON.stringify({ _tag: "CallTool", toolName: "get_current_time", args: {} }),
      })),
    )
    const result = await runButlerLoop({
      wiring,
      conversationId: "c-test-9",
      content: "loop me",
      fromUserId: "u-1",
      projectId: "p-1",
      env: {},
      logger: silentLogger,
      adapter,
    })
    expect(result.iterations).toBe(5)
    expect(result.reply).toContain("MVP stub reply")
    expect(result.traces.some((t) => t.includes("loop exhausted"))).toBe(true)
  })

  it("returns stub when the model references an unknown tool", async () => {
    const adapter = makeMockAdapter([
      {
        role: "assistant",
        content: JSON.stringify({ _tag: "CallTool", toolName: "does_not_exist", args: {} }),
      },
    ])
    const result = await runButlerLoop({
      wiring,
      conversationId: "c-test-10",
      content: "call something",
      fromUserId: "u-1",
      projectId: "p-1",
      env: {},
      logger: silentLogger,
      adapter,
    })
    expect(result.reply).toContain("MVP stub reply")
    expect(result.traces.some((t) => t.includes("unknown tool"))).toBe(true)
  })

  it("writes TurnOpened and AssistantMessageProduced events to event_store", async () => {
    const adapter = makeMockAdapter([
      { role: "assistant", content: JSON.stringify({ _tag: "Respond", content: "ok" }) },
    ])
    const result = await runButlerLoop({
      wiring,
      conversationId: "c-test-11",
      content: "hi",
      fromUserId: "u-1",
      projectId: "p-1",
      env: {},
      logger: silentLogger,
      adapter,
    })
    expect(result.reply).toBe("ok")
    const events = await bridge.loadStream("c-test-11")
    const types = events.map((e) => e.eventType)
    expect(types).toContain("TurnOpened")
    expect(types).toContain("AssistantMessageProduced")
  })
})
