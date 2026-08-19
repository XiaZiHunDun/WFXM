/**
 * R8.x.13 — conversation memory: event stream → LLM messages + compact.
 */
import { describe, expect, it, vi } from "vitest"
import { Effect } from "effect"
import type { LLMAdapter, LLMAssistantResponse } from "@butler/adapters"
import {
  compactConversationHistory,
  compactConversationHistoryWithLlm,
  eventsToHistoryMessages,
  type HistoryEvent,
} from "./conversation-memory.js"

function turn(content: string): HistoryEvent {
  return {
    eventType: "TurnOpened",
    payload: { _tag: "TurnOpened", role: "user", content },
  }
}

function assistant(content: string): HistoryEvent {
  return {
    eventType: "AssistantMessageProduced",
    payload: { _tag: "AssistantMessageProduced", content },
  }
}

function stubAdapter(content: string): LLMAdapter {
  return {
    complete: vi.fn(() =>
      Effect.succeed<LLMAssistantResponse>({
        content,
        toolCalls: [],
        stopReason: "end_turn",
      }),
    ),
  }
}

describe("eventsToHistoryMessages", () => {
  it("maps TurnOpened user and AssistantMessageProduced; skips ConversationStarted", () => {
    const msgs = eventsToHistoryMessages([
      {
        eventType: "ConversationStarted",
        payload: { content: "ignore me" },
      },
      turn("hello"),
      assistant("hi"),
    ])
    expect(msgs).toEqual([
      { role: "user", content: "hello" },
      { role: "assistant", content: "hi" },
    ])
  })

  it("drops the trailing user turn that matches the current inbound", () => {
    const msgs = eventsToHistoryMessages([turn("old"), assistant("ok"), turn("new question")], {
      currentUserContent: "new question",
    })
    expect(msgs).toEqual([
      { role: "user", content: "old" },
      { role: "assistant", content: "ok" },
    ])
  })
})

describe("compactConversationHistory", () => {
  it("keeps recent messages when under budget", () => {
    const msgs = [
      { role: "user" as const, content: "a" },
      { role: "assistant" as const, content: "b" },
    ]
    const out = compactConversationHistory(msgs, { maxMessages: 8, maxChars: 1000 })
    expect(out.messages).toEqual(msgs)
    expect(out.compacted).toBe(false)
    expect(out.source).toBe("none")
  })

  it("summarizes dropped older turns when over maxMessages", () => {
    const msgs = [
      { role: "user" as const, content: "one" },
      { role: "assistant" as const, content: "two" },
      { role: "user" as const, content: "three" },
      { role: "assistant" as const, content: "four" },
    ]
    const out = compactConversationHistory(msgs, { maxMessages: 2, maxChars: 4000 })
    expect(out.compacted).toBe(true)
    expect(out.source).toBe("extractive")
    expect(out.messages[0]?.role).toBe("system")
    expect(out.messages[0]?.content).toMatch(/Earlier conversation/)
    expect(out.messages[0]?.content).toContain("one")
    expect(out.messages.slice(-2)).toEqual([
      { role: "user", content: "three" },
      { role: "assistant", content: "four" },
    ])
  })
})

describe("compactConversationHistoryWithLlm", () => {
  const msgs = [
    { role: "user" as const, content: "one" },
    { role: "assistant" as const, content: "two" },
    { role: "user" as const, content: "three" },
    { role: "assistant" as const, content: "four" },
  ]

  it("does not call the LLM when under budget", async () => {
    const adapter = stubAdapter("should-not-run")
    const out = await compactConversationHistoryWithLlm(msgs, {
      maxMessages: 8,
      adapter,
    })
    expect(out.compacted).toBe(false)
    expect(adapter.complete).not.toHaveBeenCalled()
  })

  it("uses the LLM summary for dropped turns", async () => {
    const adapter = stubAdapter("用户叫小明，喜欢喝茶。")
    const out = await compactConversationHistoryWithLlm(msgs, {
      maxMessages: 2,
      adapter,
    })
    expect(out.compacted).toBe(true)
    expect(out.source).toBe("llm")
    expect(out.messages[0]?.content).toContain("用户叫小明")
    expect(out.messages.slice(-2).map((m) => m.content)).toEqual(["three", "four"])
    expect(adapter.complete).toHaveBeenCalledTimes(1)
  })

  it("falls back to extractive summary when the LLM fails", async () => {
    const adapter: LLMAdapter = {
      complete: () => Effect.fail(new Error("summarizer down")),
    }
    const out = await compactConversationHistoryWithLlm(msgs, {
      maxMessages: 2,
      adapter,
    })
    expect(out.source).toBe("extractive")
    expect(out.messages[0]?.content).toContain("one")
  })
})
