import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { Effect } from "effect"
import type { LLMAdapter, LLMAssistantResponse } from "@butler/adapters"
import { EventBridge } from "@butler/runtime/bridge.js"
import { makeTestDb } from "@butler/persistence/testing.js"
import { makeWiring, type Wiring } from "./wiring.js"
import { runButlerLoop, type ButlerLoopLogger } from "./wechat-inbound-butler.js"

/**
 * Build a mock adapter that returns a sequence of pre-canned
 * `LLMAssistantResponse` values. Each call to `complete` pops the
 * next response; if exhausted, returns an empty text-only response.
 */
function makeMockAdapter(replies: readonly LLMAssistantResponse[]): LLMAdapter {
  let i = 0
  return {
    complete: vi.fn((_messages, _opts) =>
      Effect.succeed(replies[i++] ?? { content: "", toolCalls: [], stopReason: "stop" }),
    ),
  }
}

/** Convenience: build a text-only assistant response. */
function textResponse(content: string): LLMAssistantResponse {
  return { content, toolCalls: [], stopReason: "end_turn" }
}

/** Convenience: build a native tool_call response. */
function toolCallResponse(
  toolCalls: readonly {
    readonly id: string
    readonly name: string
    readonly args: Record<string, unknown>
  }[],
  content = "",
): LLMAssistantResponse {
  return { content, toolCalls, stopReason: "tool_use" }
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

  it("returns Respond content when the model emits a Respond decision (JSON-decision fallback)", async () => {
    const adapter = makeMockAdapter([
      textResponse(JSON.stringify({ _tag: "Respond", content: "hi back" })),
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
    const adapter = makeMockAdapter([textResponse("plain text reply")])
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

  it("executes a native OpenAI-style tool_call and returns the model's follow-up Respond", async () => {
    const adapter = makeMockAdapter([
      toolCallResponse([{ id: "tc_1", name: "get_current_time", args: {} }]),
      textResponse("now is the time"),
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

  it("executes greet_with_time (native tool_call) and feeds the greeting back", async () => {
    const adapter = makeMockAdapter([
      toolCallResponse([{ id: "tc_greet", name: "greet_with_time", args: {} }]),
      textResponse("你好呀"),
    ])
    const result = await runButlerLoop({
      wiring,
      conversationId: "c-test-greet",
      content: "hi",
      fromUserId: "u-1",
      projectId: "p-1",
      env: {},
      logger: silentLogger,
      adapter,
    })
    expect(result.reply).toBe("你好呀")
    expect(result.toolCalls).toBe(1)
    expect(result.traces.some((t) => t.startsWith("greet_with_time@"))).toBe(true)
  })

  it("executes summarize_today (native tool_call) and feeds the summary back", async () => {
    const adapter = makeMockAdapter([
      toolCallResponse([{ id: "tc_sum", name: "summarize_today", args: {} }]),
      textResponse("今天没做什么"),
    ])
    const result = await runButlerLoop({
      wiring,
      conversationId: "c-test-sum",
      content: "今天做了什么",
      fromUserId: "u-1",
      projectId: "p-1",
      env: {},
      logger: silentLogger,
      adapter,
    })
    expect(result.reply).toBe("今天没做什么")
    expect(result.toolCalls).toBe(1)
    expect(result.traces.some((t) => t.startsWith("summarize_today@"))).toBe(true)
  })

  it("executes a native Anthropic-style tool_use and feeds the result back", async () => {
    const adapter = makeMockAdapter([
      toolCallResponse([{ id: "tu_1", name: "get_current_time", args: {} }]),
      textResponse("the current time is 2026-08-15"),
    ])
    const result = await runButlerLoop({
      wiring,
      conversationId: "c-test-anthropic-1",
      content: "what time is it?",
      fromUserId: "u-1",
      projectId: "p-1",
      env: {},
      logger: silentLogger,
      adapter,
    })
    expect(result.reply).toBe("the current time is 2026-08-15")
    expect(result.toolCalls).toBe(1)
    expect(result.iterations).toBe(2)
    expect(result.traces.some((t) => t.startsWith("get_current_time@"))).toBe(true)
  })

  it("passes WEIBUTLER_LLM_TOOLS to the adapter on every call", async () => {
    const completeSpy = vi.fn(() => Effect.succeed(textResponse("ok") as LLMAssistantResponse))
    const adapter: LLMAdapter = { complete: completeSpy }
    await runButlerLoop({
      wiring,
      conversationId: "c-test-tools-pass",
      content: "hi",
      fromUserId: "u-1",
      projectId: "p-1",
      env: {},
      logger: silentLogger,
      adapter,
    })
    expect(completeSpy).toHaveBeenCalledTimes(1)
    const opts = completeSpy.mock.calls[0]?.[1] as
      { readonly tools?: readonly { readonly name: string }[] } | undefined
    expect(opts?.tools).toBeDefined()
    const names = (opts?.tools ?? []).map((t) => t.name).sort()
    expect(names).toEqual([
      "delegate_to_subagent",
      "get_current_time",
      "greet_with_time",
      "recall_history",
      "summarize_today",
    ])
  })

  it("echoes assistant.toolCalls back as a message and pushes tool result messages", async () => {
    let lastMessages: readonly Record<string, unknown>[] = []
    let calls = 0
    const adapter: LLMAdapter = {
      complete: vi.fn((msgs, _opts) => {
        lastMessages = msgs as readonly Record<string, unknown>[]
        calls += 1
        if (calls === 1) {
          return Effect.succeed(
            toolCallResponse([{ id: "tc_1", name: "get_current_time", args: {} }]),
          )
        }
        return Effect.succeed(textResponse("done"))
      }),
    }
    await runButlerLoop({
      wiring,
      conversationId: "c-test-echo",
      content: "what time?",
      fromUserId: "u-1",
      projectId: "p-1",
      env: {},
      logger: silentLogger,
      adapter,
    })
    expect(calls).toBe(2)
    // Second call: messages should now contain assistant(toolCalls)
    // and tool messages.
    const roles = lastMessages.map((m) => m["role"])
    expect(roles).toContain("assistant")
    expect(roles).toContain("tool")
    const assistant = lastMessages.find((m) => m["role"] === "assistant")
    expect(assistant?.["toolCalls"]).toBeDefined()
    expect(assistant?.["content"]).toBe("")
    const tool = lastMessages.find((m) => m["role"] === "tool")
    expect(tool?.["toolCallId"]).toBe("tc_1")
    expect(tool?.["toolName"]).toBe("get_current_time")
  })

  it("executes recall_history (native tool_call) with limit and feeds result back", async () => {
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
      toolCallResponse([{ id: "tc_recall", name: "recall_history", args: { limit: 3 } }]),
      textResponse("I recall earlier msg"),
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

  it("runs multiple native tool_calls in one assistant turn", async () => {
    const adapter = makeMockAdapter([
      toolCallResponse([
        { id: "tc_a", name: "get_current_time", args: {} },
        { id: "tc_b", name: "recall_history", args: { limit: 2 } },
      ]),
      textResponse("both done"),
    ])
    const result = await runButlerLoop({
      wiring,
      conversationId: "c-test-multi",
      content: "time and history?",
      fromUserId: "u-1",
      projectId: "p-1",
      env: {},
      logger: silentLogger,
      adapter,
    })
    expect(result.reply).toBe("both done")
    expect(result.toolCalls).toBe(2)
    expect(result.iterations).toBe(2)
  })

  it("runs legacy JSON-decision CallTool as a fallback when no native tool_calls", async () => {
    const adapter = makeMockAdapter([
      textResponse(JSON.stringify({ _tag: "CallTool", toolName: "get_current_time", args: {} })),
      textResponse(JSON.stringify({ _tag: "Respond", content: "now is the time" })),
    ])
    const result = await runButlerLoop({
      wiring,
      conversationId: "c-test-legacy",
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

  it("falls back to stub on Finish decision", async () => {
    const adapter = makeMockAdapter([
      textResponse(JSON.stringify({ _tag: "Finish", reason: "all done" })),
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
      textResponse(JSON.stringify({ _tag: "AskApproval", question: "delete?" })),
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
      Array.from({ length: 10 }, () =>
        toolCallResponse([{ id: "tc_loop", name: "get_current_time", args: {} }]),
      ),
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

  it("returns stub when the model requests an unknown tool via native tool_calls", async () => {
    const adapter = makeMockAdapter([
      toolCallResponse([{ id: "tc_bad", name: "does_not_exist", args: {} }]),
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
    // Unknown native tool_call pushes error result then loops again;
    // empty follow-up response → fall back to stub via loop iteration.
    expect(result.reply).toContain("MVP stub reply")
    expect(result.traces.some((t) => t.includes("unknown tool"))).toBe(true)
  })

  it("writes TurnOpened and AssistantMessageProduced events to event_store", async () => {
    const adapter = makeMockAdapter([
      textResponse(JSON.stringify({ _tag: "Respond", content: "ok" })),
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

  it("handles a Delegate JSON-decision: writes ChildRunCreated, loops back to Respond", async () => {
    const adapter = makeMockAdapter([
      textResponse(
        JSON.stringify({ _tag: "Delegate", role: "researcher", task: "find docs about Foo" }),
      ),
      textResponse(JSON.stringify({ _tag: "Respond", content: "已委派给 researcher 子代理" })),
    ])
    const result = await runButlerLoop({
      wiring,
      conversationId: "c-test-delegate-1",
      content: "帮我找 Foo 的文档",
      fromUserId: "u-1",
      projectId: "p-1",
      env: {},
      logger: silentLogger,
      adapter,
    })
    expect(result.reply).toBe("已委派给 researcher 子代理")
    expect(result.finalDecision).toBe("Respond")
    expect(result.toolCalls).toBe(1)
    expect(result.iterations).toBe(2)
    expect(result.traces.some((t) => t.startsWith("delegate_to_subagent@"))).toBe(true)
    const events = await bridge.loadStream("c-test-delegate-1")
    const childEvents = events.filter((e) => e.eventType === "ChildRunCreated")
    expect(childEvents.length).toBe(1)
  })

  it("handles a Delegate JSON-decision and falls back to stub when follow-up fails", async () => {
    // Delegate then empty text response — loop continues, then stub.
    const adapter = makeMockAdapter([
      textResponse(JSON.stringify({ _tag: "Delegate", role: "general", task: "do thing" })),
      textResponse(""),
    ])
    const result = await runButlerLoop({
      wiring,
      conversationId: "c-test-delegate-2",
      content: "复杂任务要委派给子代理",
      fromUserId: "u-1",
      projectId: "p-1",
      env: {},
      logger: silentLogger,
      adapter,
    })
    expect(result.toolCalls).toBe(1)
    expect(result.traces.some((t) => t.startsWith("delegate_to_subagent@"))).toBe(true)
  })

  it("dispatches delegate_to_subagent via native tool_calls and feeds result back", async () => {
    const adapter = makeMockAdapter([
      toolCallResponse([
        {
          id: "tc_delegate",
          name: "delegate_to_subagent",
          args: { task: "long-running analysis", role: "developer" },
        },
      ]),
      textResponse(JSON.stringify({ _tag: "Respond", content: "已委派开发子代理" })),
    ])
    const result = await runButlerLoop({
      wiring,
      conversationId: "c-test-delegate-native",
      content: "请帮我跑个长任务",
      fromUserId: "u-1",
      projectId: "p-1",
      env: {},
      logger: silentLogger,
      adapter,
    })
    expect(result.reply).toBe("已委派开发子代理")
    expect(result.finalDecision).toBe("Respond")
    expect(result.toolCalls).toBe(1)
    expect(result.iterations).toBe(2)
    expect(result.traces.some((t) => t.startsWith("delegate_to_subagent@"))).toBe(true)
    const events = await bridge.loadStream("c-test-delegate-native")
    expect(events.some((e) => e.eventType === "ChildRunCreated")).toBe(true)
  })
})
