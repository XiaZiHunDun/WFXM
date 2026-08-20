import { describe, expect, it } from "vitest"
import { buildWorkingSet } from "./working-set.js"

function userMessage(index: number, text: string) {
  return {
    id: `m-${index}`,
    conversationId: "c-1",
    role: "user" as const,
    content: { text },
    triggerSource: "channel" as const,
    idempotencyKey: `k-${index}`,
    createdAt: new Date(`2026-08-20T00:${String(index).padStart(2, "0")}:00Z`),
  }
}

function assistantMessage(index: number, text: string) {
  return {
    id: `m-${index}`,
    conversationId: "c-1",
    role: "assistant" as const,
    content: { text },
    triggerSource: null,
    idempotencyKey: null,
    createdAt: new Date(`2026-08-20T00:${String(index).padStart(2, "0")}:00Z`),
  }
}

describe("buildWorkingSet", () => {
  it("keeps recent turns within budget and summarizes older ones", () => {
    const messages = Array.from({ length: 20 }, (_, i) =>
      i % 2 === 0
        ? userMessage(i, `question ${i} `.repeat(8))
        : assistantMessage(i, `answer ${i} `.repeat(8)),
    )
    const result = buildWorkingSet({
      messages,
      trailingUserContent: "latest question",
      budget: { maxMessages: 6, maxChars: 800 },
    })

    expect(result.compacted).toBe(true)
    expect(result.source).toBe("extractive")
    expect(result.droppedCount).toBeGreaterThan(0)
    expect(result.messages[0]?.role).toBe("system")
    expect(result.messages.at(-1)).toEqual({ role: "user", content: "latest question" })
    expect(result.messages.length).toBeLessThan(messages.length + 2)
  })

  it("does not drop the trailing user turn when it matches stored history", () => {
    const messages = [userMessage(1, "hello"), assistantMessage(2, "hi")]
    const result = buildWorkingSet({
      messages: [...messages, userMessage(3, "again")],
      trailingUserContent: "again",
      budget: { maxMessages: 10, maxChars: 4000 },
    })

    expect(result.messages.filter((m) => m.role === "user" && m.content === "again")).toHaveLength(
      1,
    )
  })

  it("handles 120+ turns without deleting stored messages", () => {
    const messages = Array.from({ length: 140 }, (_, i) =>
      i % 2 === 0 ? userMessage(i, `u-${i}`) : assistantMessage(i, `a-${i}`),
    )
    const result = buildWorkingSet({
      messages,
      trailingUserContent: "turn-140",
      budget: { maxMessages: 12, maxChars: 2000 },
    })

    expect(messages).toHaveLength(140)
    expect(result.compacted).toBe(true)
    expect(result.droppedCount).toBeGreaterThan(100)
    expect(result.messages.at(-1)).toEqual({ role: "user", content: "turn-140" })
  })

  it("falls back to extractive summary when no adapter is available", () => {
    const messages = Array.from({ length: 30 }, (_, i) => userMessage(i, `msg-${i} `.repeat(10)))
    const result = buildWorkingSet({
      messages,
      budget: { maxMessages: 4, maxChars: 300 },
    })

    expect(result.source).toBe("extractive")
    expect(result.messages[0]?.content).toContain("Earlier conversation")
  })
})
