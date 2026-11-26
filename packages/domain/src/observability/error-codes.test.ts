import { describe, expect, it } from "vitest"
import { ERROR_CODES, formatFailureEnvelope, resolveErrorCode, turnIdShort } from "./error-codes.js"

describe("resolveErrorCode", () => {
  it("maps known error _tags", () => {
    expect(resolveErrorCode({ _tag: "LLMUnavailable" })).toBe("E-LLM-01")
    expect(resolveErrorCode({ _tag: "ContextOverflow" })).toBe("E-CTX-01")
    expect(resolveErrorCode({ _tag: "ToolFailed" })).toBe("E-TOOL-01")
    expect(resolveErrorCode({ _tag: "GuardRejected" })).toBe("E-POL-01")
    expect(resolveErrorCode({ _tag: "ActiveMainRunConflict" })).toBe("E-RUN-01")
    expect(resolveErrorCode({ _tag: "CompletedMainRunReplay" })).toBe("E-RUN-01")
    expect(resolveErrorCode({ _tag: "PersistenceFailed" })).toBe("E-DB-01")
    expect(resolveErrorCode({ _tag: "InvalidRunTrigger" })).toBe("E-REQ-01")
  })

  it("falls back to keyword matching on the message", () => {
    expect(resolveErrorCode(new Error("fetch failed: ECONNREFUSED"))).toBe("E-LLM-01")
    expect(resolveErrorCode(new Error("maximum context length exceeded"))).toBe("E-CTX-01")
    expect(resolveErrorCode(new Error("postgres deadlock detected"))).toBe("E-DB-01")
    expect(resolveErrorCode(new Error("approval denied by policy"))).toBe("E-POL-01")
    expect(resolveErrorCode(new Error("invalid body"))).toBe("E-REQ-01")
    expect(resolveErrorCode(new Error("tool execution failed"))).toBe("E-TOOL-01")
  })

  it("uses the constructor name when no _tag is present", () => {
    class LLMUnavailable extends Error {}
    expect(resolveErrorCode(new LLMUnavailable("boom"))).toBe("E-LLM-01")
  })

  it("falls back to E-INT-01 for unknown values", () => {
    expect(resolveErrorCode(null)).toBe("E-INT-01")
    expect(resolveErrorCode(undefined)).toBe("E-INT-01")
    expect(resolveErrorCode(42)).toBe("E-INT-01")
    expect(resolveErrorCode(new Error("something odd"))).toBe("E-INT-01")
  })
})

describe("turnIdShort", () => {
  it("returns the first 8 characters", () => {
    expect(turnIdShort("turn-1723456789")).toBe("turn-172")
    expect(turnIdShort("short")).toBe("short")
    expect(turnIdShort("123456789")).toBe("12345678")
  })

  it("handles empty / nullish input", () => {
    expect(turnIdShort(null)).toBe("")
    expect(turnIdShort(undefined)).toBe("")
    expect(turnIdShort("   ")).toBe("")
  })
})

describe("formatFailureEnvelope", () => {
  it("includes code and truncated turn id", () => {
    const text = formatFailureEnvelope({ code: "E-LLM-01", turnId: "turn-1723456789" })
    expect(text.startsWith("[E-LLM-01 · turn-172]")).toBe(true)
    expect(text).toContain("处理失败，已记录")
  })

  it("omits the turn id segment when unavailable", () => {
    const text = formatFailureEnvelope({ code: "E-INT-01" })
    expect(text.startsWith("[E-INT-01]")).toBe(true)
    expect(text).not.toContain("·")
  })

  it("never leaks raw exception text", () => {
    const text = formatFailureEnvelope({ code: "E-DB-01", turnId: "turn-abcdefgh" })
    expect(text).not.toMatch(/stack|Error:|postgres/i)
  })

  it("F17: a delegated turn says the task is running instead of asking for a resend", () => {
    const text = formatFailureEnvelope({
      code: "E-LLM-01",
      turnId: "turn-1723456789",
      delegated: true,
    })
    expect(text).toContain("已交给后台执行")
    expect(text).not.toContain("请稍后再发一次")
    expect(text).toContain("不要原样重发")
  })

  it("F17: a turn that already ran tools reports partial effects", () => {
    const text = formatFailureEnvelope({ code: "E-LLM-01", turnId: "turn-1", toolCalls: 3 })
    expect(text).toContain("3 次操作")
    expect(text).not.toContain("请稍后再发一次")
  })
})

describe("ERROR_CODES registry", () => {
  it("covers every declared code with a title and hint", () => {
    for (const info of Object.values(ERROR_CODES)) {
      expect(info.title.length).toBeGreaterThan(0)
      expect(info.ownerHint.length).toBeGreaterThan(0)
      expect(info.code).toBe(info.code.toUpperCase())
    }
  })
})
