import { describe, expect, it } from "vitest"
import {
  buildDeepSeekRequestExtras,
  isDeepSeekV4Model,
  resolveDeepSeekThinkingType,
} from "./deepseek-request.js"

describe("deepseek-request", () => {
  it("detects V4 model ids", () => {
    expect(isDeepSeekV4Model("deepseek-v4-flash")).toBe(true)
    expect(isDeepSeekV4Model("deepseek-v4-pro")).toBe(true)
    expect(isDeepSeekV4Model("deepseek-chat")).toBe(false)
  })

  it("defaults V4 thinking to disabled", () => {
    expect(resolveDeepSeekThinkingType({}, "deepseek-v4-flash")).toBe("disabled")
    expect(buildDeepSeekRequestExtras({}, "deepseek-v4-flash")).toEqual({
      thinking: { type: "disabled" },
    })
  })

  it("allows opt-in enabled thinking", () => {
    expect(
      resolveDeepSeekThinkingType({ BUTLER_V5_DEEPSEEK_THINKING: "enabled" }, "deepseek-v4-flash"),
    ).toBe("enabled")
  })

  it("skips thinking toggle for legacy deepseek-chat", () => {
    expect(resolveDeepSeekThinkingType({}, "deepseek-chat")).toBeNull()
    expect(buildDeepSeekRequestExtras({}, "deepseek-chat")).toBeUndefined()
  })
})
