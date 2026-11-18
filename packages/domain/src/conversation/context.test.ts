import { describe, it, expect } from "vitest"
import { chooseStrategy, makeContextWindow, isNearLimit } from "./context.js"

describe("conversation/context", () => {
  describe("chooseStrategy", () => {
    it("returns summarize when tokens > 90% max", () => {
      const window = { tokens: 190_000, maxTokens: 200_000, compressed: false }
      expect(chooseStrategy(window)).toBe("summarize")
    })

    it("returns truncate when tokens > 70% max", () => {
      const window = { tokens: 160_000, maxTokens: 200_000, compressed: false }
      expect(chooseStrategy(window)).toBe("truncate")
    })

    it("returns summarize by default", () => {
      const window = { tokens: 100_000, maxTokens: 200_000, compressed: false }
      expect(chooseStrategy(window)).toBe("summarize")
    })
  })

  describe("isNearLimit", () => {
    it("returns true when tokens exceed threshold", () => {
      const window = makeContextWindow(180_000, 200_000)
      expect(isNearLimit(window)).toBe(true)
    })

    it("returns false when tokens are below threshold", () => {
      const window = makeContextWindow(100_000, 200_000)
      expect(isNearLimit(window)).toBe(false)
    })

    it("accepts custom threshold", () => {
      const window = makeContextWindow(100_000, 200_000)
      expect(isNearLimit(window, 0.49)).toBe(true)
      expect(isNearLimit(window, 0.5)).toBe(false)
    })
  })

  describe("makeContextWindow", () => {
    it("creates window with given tokens", () => {
      const window = makeContextWindow(50000, 100000)
      expect(window.tokens).toBe(50000)
      expect(window.maxTokens).toBe(100000)
      expect(window.compressed).toBe(false)
    })
  })
})
