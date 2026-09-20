import { describe, expect, it } from "vitest"
import { safeCompareTrimmedSecrets, timingSafeEqualStrings } from "./secure-compare.js"

describe("timingSafeEqualStrings", () => {
  it("returns true for equal strings", () => {
    expect(timingSafeEqualStrings("abc123", "abc123")).toBe(true)
  })

  it("returns false for unequal strings of the same length", () => {
    expect(timingSafeEqualStrings("abc123", "abc124")).toBe(false)
  })

  it("throws when lengths differ (mirrors crypto.timingSafeEqual)", () => {
    expect(() => timingSafeEqualStrings("abc", "abcd")).toThrow()
  })
})

describe("safeCompareTrimmedSecrets (D73 SEC-004)", () => {
  it("returns true when trimmed values are equal", () => {
    expect(safeCompareTrimmedSecrets("shared-secret", "shared-secret")).toBe(true)
  })

  it("trims both sides before comparing", () => {
    expect(safeCompareTrimmedSecrets("  shared-secret  ", "shared-secret")).toBe(true)
    expect(safeCompareTrimmedSecrets("shared-secret", "  shared-secret\n")).toBe(true)
  })

  it("returns false on length mismatch without throwing", () => {
    expect(safeCompareTrimmedSecrets("abc", "abcd")).toBe(false)
    expect(safeCompareTrimmedSecrets("abcd", "abc")).toBe(false)
  })

  it("returns false when trimmed values differ", () => {
    expect(safeCompareTrimmedSecrets("shared-secret", "different-secret")).toBe(false)
  })

  it("returns false when either side is empty after trim", () => {
    expect(safeCompareTrimmedSecrets("", "anything")).toBe(false)
    expect(safeCompareTrimmedSecrets("anything", "")).toBe(false)
    expect(safeCompareTrimmedSecrets("", "")).toBe(false)
    expect(safeCompareTrimmedSecrets("   ", "   ")).toBe(false)
  })
})