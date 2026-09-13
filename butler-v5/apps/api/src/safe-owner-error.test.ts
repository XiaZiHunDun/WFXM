import { describe, expect, it, vi } from "vitest"
import { safeOwnerError } from "./safe-owner-error.js"

describe("safeOwnerError", () => {
  it("returns the fallback string verbatim — never leaks err.message", () => {
    const result = safeOwnerError(
      new Error("connection refused on 127.0.0.1:5432"),
      "数据库暂时不可用，请稍后重试",
    )
    expect(result).toBe("数据库暂时不可用，请稍后重试")
  })

  it("logs structured error context to stderr for operators", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {})
    try {
      safeOwnerError(new Error("EACCES /var/run/butler.sock"), "操作失败", {
        operation: "swap-active",
        projectId: "WFXM",
      })
      expect(spy).toHaveBeenCalledOnce()
      const [tag, payload] = spy.mock.calls[0] as [string, Record<string, unknown>]
      expect(tag).toBe("[safe-owner-error]")
      expect(payload).toMatchObject({
        name: "Error",
        message: "EACCES /var/run/butler.sock",
        fallback: "操作失败",
        context: { operation: "swap-active", projectId: "WFXM" },
      })
      expect(typeof payload.stack).toBe("string")
    } finally {
      spy.mockRestore()
    }
  })

  it("handles non-Error throws (strings, numbers, plain objects)", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {})
    try {
      // String throw
      expect(safeOwnerError("boom", "失败")).toBe("失败")
      // Number throw
      expect(safeOwnerError(42, "失败")).toBe("失败")
      // Plain object throw
      expect(safeOwnerError({ code: "X" }, "失败")).toBe("失败")

      // Verify each captured value, not err.message, in the log
      const calls = spy.mock.calls as [string, Record<string, unknown>][]
      expect(calls[0][1]).toMatchObject({ value: "boom" })
      expect(calls[1][1]).toMatchObject({ value: "42" })
      expect(calls[2][1]).toMatchObject({ value: "[object Object]" })
    } finally {
      spy.mockRestore()
    }
  })

  it("treats context=undefined as null in the log payload", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {})
    try {
      safeOwnerError(new Error("x"), "fallback")
      const payload = spy.mock.calls[0][1] as Record<string, unknown>
      expect(payload.context).toBeNull()
    } finally {
      spy.mockRestore()
    }
  })

  it("never throws on weird inputs (null, undefined)", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {})
    try {
      expect(() => safeOwnerError(null, "fallback")).not.toThrow()
      expect(() => safeOwnerError(undefined, "fallback")).not.toThrow()
      expect(safeOwnerError(null, "fallback")).toBe("fallback")
      expect(safeOwnerError(undefined, "fallback")).toBe("fallback")
    } finally {
      spy.mockRestore()
    }
  })
})
