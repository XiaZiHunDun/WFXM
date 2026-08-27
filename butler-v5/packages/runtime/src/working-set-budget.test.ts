import { describe, expect, it } from "vitest"
import {
  filterDevHistoryNoise,
  resolveWorkingSetBudget,
  workingSetModeFromTriggerPayload,
} from "./working-set-budget.js"

describe("working-set-budget", () => {
  it("uses larger dev defaults", () => {
    const chat = resolveWorkingSetBudget({}, "default")
    const dev = resolveWorkingSetBudget({}, "dev")
    expect(dev.maxMessages).toBeGreaterThan(chat.maxMessages ?? 0)
    expect(dev.maxChars).toBeGreaterThan(chat.maxChars ?? 0)
  })

  it("reads env overrides", () => {
    const dev = resolveWorkingSetBudget(
      {
        BUTLER_V5_DEV_WORKING_SET_MAX_MESSAGES: "24",
        BUTLER_V5_DEV_WORKING_SET_MAX_CHARS: "12000",
      },
      "dev",
    )
    expect(dev.maxMessages).toBe(24)
    expect(dev.maxChars).toBe(12000)
  })

  it("parses workingSetMode from trigger payload", () => {
    expect(workingSetModeFromTriggerPayload({ workingSetMode: "dev" })).toBe("dev")
    expect(workingSetModeFromTriggerPayload({})).toBe("default")
  })

  it("filters chat noise from older dev history", () => {
    const messages = [
      { id: "1", role: "user" as const, content: { text: "ping" } },
      { id: "2", role: "assistant" as const, content: { text: "pong" } },
      { id: "3", role: "user" as const, content: { text: "pwd" } },
      { id: "4", role: "assistant" as const, content: { text: "/home" } },
      { id: "5", role: "user" as const, content: { text: "帮我实现缓存模块" } },
      { id: "6", role: "assistant" as const, content: { text: "好的" } },
    ].map((m, i) => ({
      ...m,
      conversationId: "c-1",
      triggerSource: "channel" as const,
      idempotencyKey: `k-${i}`,
      createdAt: new Date(`2026-08-20T00:0${i}:00Z`),
    }))
    const filtered = filterDevHistoryNoise(messages, { keepTail: 2 })
    expect(filtered.map((m) => m.id)).toEqual(["2", "4", "5", "6"])
  })
})
