import { describe, expect, it } from "vitest"
import { estimateTokens, planCompression, type Message } from "./context-manager.js"

describe("ContextManager", () => {
  it("estimates tokens roughly as chars / 4", () => {
    const m: Message = { role: "user", content: "x".repeat(40) }
    expect(estimateTokens([m])).toBe(10)
  })

  it("handles empty message list", () => {
    expect(estimateTokens([])).toBe(0)
  })

  it("plans no compression when within budget", () => {
    const msgs: Message[] = [{ role: "user", content: "short" }]
    const plan = planCompression(msgs, { budgetTokens: 1000 })
    expect(plan.compress).toBe(false)
    expect(plan.estimatedTokens).toBeLessThan(1000)
    expect(plan.reason).toMatch(/budget/i)
  })

  it("plans compression when over budget", () => {
    const msgs: Message[] = [
      { role: "user", content: "x".repeat(4000) },
      { role: "assistant", content: "y".repeat(4000) },
    ]
    const plan = planCompression(msgs, { budgetTokens: 100 })
    expect(plan.compress).toBe(true)
    expect(plan.estimatedTokens).toBeGreaterThan(100)
    expect(plan.keepFirst + plan.keepLast).toBeLessThan(msgs.length)
    expect(plan.reason).toMatch(/over budget/i)
  })

  it("respects custom charsPerToken", () => {
    const msgs: Message[] = [{ role: "user", content: "x".repeat(40) }]
    expect(estimateTokens(msgs, 5)).toBe(8)
  })

  it("does not compress at the exact budget boundary", () => {
    const msgs: Message[] = [{ role: "user", content: "x".repeat(400) }]
    const plan = planCompression(msgs, { budgetTokens: 100 })
    expect(plan.compress).toBe(false)
    expect(plan.estimatedTokens).toBe(100)
    expect(plan.keepFirst).toBe(1)
  })

  it("degenerates to keep nothing for a single over-budget message", () => {
    const msgs: Message[] = [{ role: "user", content: "x".repeat(800) }]
    const plan = planCompression(msgs, { budgetTokens: 100 })
    expect(plan.compress).toBe(true)
    expect(plan.keepFirst).toBe(0)
    expect(plan.keepLast).toBe(0)
    expect(plan.reason).toMatch(/over budget/i)
  })
})
