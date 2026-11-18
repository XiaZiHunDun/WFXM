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

  it("returns only the system prefix and trailing turn for an empty history", () => {
    const result = buildWorkingSet({
      systemPrefix: [{ role: "system", content: "You are Butler" }],
      messages: [],
      trailingUserContent: "hi",
    })
    expect(result.messages).toEqual([
      { role: "system", content: "You are Butler" },
      { role: "user", content: "hi" },
    ])
    expect(result.compacted).toBe(false)
    expect(result.droppedCount).toBe(0)
  })

  it("includes capability/model run steps and filters out other step kinds", () => {
    const result = buildWorkingSet({
      messages: [],
      currentRunSteps: [
        {
          id: "s1",
          runId: "r1",
          kind: "capability",
          status: "succeeded",
          input: { name: "read_file" },
          output: { ok: true },
          createdAt: new Date("2026-08-20T00:00:00Z"),
          updatedAt: new Date("2026-08-20T00:00:00Z"),
        },
        {
          id: "s2",
          runId: "r1",
          kind: "approval",
          status: "waiting",
          input: {},
          output: null,
          createdAt: new Date("2026-08-20T00:00:00Z"),
          updatedAt: new Date("2026-08-20T00:00:00Z"),
        },
        {
          id: "s3",
          runId: "r1",
          kind: "model",
          status: "succeeded",
          input: { prompt: "summarize" },
          output: null,
          createdAt: new Date("2026-08-20T00:00:00Z"),
          updatedAt: new Date("2026-08-20T00:00:00Z"),
        },
      ],
      trailingUserContent: "go",
    })
    const stepLines = result.messages.filter((m) => m.content.startsWith("[run-step:"))
    expect(stepLines).toHaveLength(2)
    expect(stepLines.find((m) => m.content.startsWith("[run-step:s1]"))?.role).toBe("system")
    expect(stepLines.find((m) => m.content.startsWith("[run-step:s3]"))?.content).toContain(
      "summarize",
    )
  })

  it("truncates long tool results into a reference", () => {
    const long = "x".repeat(300)
    const result = buildWorkingSet({
      messages: [
        {
          id: "m-tool",
          conversationId: "c-1",
          role: "tool",
          content: { text: long },
          triggerSource: null,
          idempotencyKey: null,
          createdAt: new Date("2026-08-20T00:00:00Z"),
        },
      ],
    })
    expect(result.messages).toHaveLength(1)
    expect(result.messages[0]?.content.startsWith("[tool-result-ref:m-tool]")).toBe(true)
    expect(result.messages[0]?.content.length).toBeLessThan(160)
  })

  it("drops by char budget when a single message is very long", () => {
    const big = "y".repeat(300)
    const result = buildWorkingSet({
      messages: [userMessage(1, "small"), userMessage(2, big)],
      budget: { maxMessages: 10, maxChars: 100 },
      trailingUserContent: "q",
    })
    expect(result.compacted).toBe(true)
    expect(result.droppedCount).toBe(1)
    expect(result.messages.some((m) => m.content.includes("- user: small"))).toBe(true)
  })

  it("extracts body content and falls back to JSON for opaque content", () => {
    const result = buildWorkingSet({
      messages: [
        {
          id: "m1",
          conversationId: "c-1",
          role: "user",
          content: { body: "from body" },
          triggerSource: null,
          idempotencyKey: null,
          createdAt: new Date("2026-08-20T00:00:00Z"),
        },
        {
          id: "m2",
          conversationId: "c-1",
          role: "user",
          content: { other: 1 },
          triggerSource: null,
          idempotencyKey: null,
          createdAt: new Date("2026-08-20T00:00:00Z"),
        },
      ],
    })
    const contents = result.messages.map((m) => m.content)
    expect(contents).toContain("from body")
    expect(contents).toContain(JSON.stringify({ other: 1 }))
  })
})
