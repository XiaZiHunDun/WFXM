import { describe, expect, it } from "vitest"
import { isDeepSeekModelName, resolveModelForRole } from "./model-port.js"

const empty: NodeJS.ProcessEnv = {}

describe("model-port (P5 Model Port — 角色级 provider+model 单一真相源)", () => {
  describe("plan", () => {
    it("returns Anthropic default model when ANTHROPIC_API_KEY set", () => {
      expect(resolveModelForRole({ ANTHROPIC_API_KEY: "sk-1", ...empty })).toEqual({
        provider: "anthropic",
        model: "claude-sonnet-4-20250514",
      })
    })

    it("honors ANTHROPIC_MODEL override", () => {
      expect(
        resolveModelForRole({
          ANTHROPIC_API_KEY: "sk-1",
          ANTHROPIC_MODEL: "claude-haiku-4-5-20251001",
          ...empty,
        }),
      ).toEqual({ provider: "anthropic", model: "claude-haiku-4-5-20251001" })
    })

    it("returns DeepSeek (default deepseek-flash) when only DEEPSEEK_API_KEY set", () => {
      expect(resolveModelForRole({ DEEPSEEK_API_KEY: "ds-1", ...empty })).toEqual({
        provider: "deepseek",
        model: "deepseek-flash",
      })
    })

    it("honors BUTLER_V5_MODEL_PLAN / DEEPSEEK_MODEL for DeepSeek model", () => {
      expect(
        resolveModelForRole({
          DEEPSEEK_API_KEY: "ds-1",
          BUTLER_V5_MODEL_PLAN: "deepseek-v4-x",
          ...empty,
        }),
      ).toEqual({ provider: "deepseek", model: "deepseek-v4-x" })
    })

    it("returns DashScope qwen-turbo when only DASHSCOPE_API_KEY set", () => {
      expect(resolveModelForRole({ DASHSCOPE_API_KEY: "dq-1", ...empty })).toEqual({
        provider: "dashscope",
        model: "qwen-turbo",
      })
    })

    it("P2 2026-09-04: returns MiniMax when only MINIMAX_API_KEY set", () => {
      expect(resolveModelForRole({ MINIMAX_API_KEY: "sk-mm", ...empty })).toEqual({
        provider: "minimax",
        model: "MiniMax-M3.1-Flash",
      })
    })

    it("P2 2026-09-04: honors BUTLER_V5_MODEL_PLAN / MINIMAX_MODEL for plan", () => {
      expect(
        resolveModelForRole({
          MINIMAX_API_KEY: "sk-mm",
          BUTLER_V5_MODEL_PLAN: "abab6.5",
          ...empty,
        }),
      ).toEqual({ provider: "minimax", model: "abab6.5" })
    })

    it("routes deepseek-name plan model to DeepSeek when both keys exist", () => {
      expect(
        resolveModelForRole({
          DEEPSEEK_API_KEY: "ds-1",
          MINIMAX_API_KEY: "sk-mm",
          BUTLER_V5_MODEL_PLAN: "deepseek-v4-flash",
          ...empty,
        }),
      ).toEqual({ provider: "deepseek", model: "deepseek-v4-flash" })
    })

    it("routes minimax-name plan model to MiniMax when both keys exist", () => {
      expect(
        resolveModelForRole({
          DEEPSEEK_API_KEY: "ds-1",
          MINIMAX_API_KEY: "sk-mm",
          BUTLER_V5_MODEL_PLAN: "MiniMax-M3",
          ...empty,
        }),
      ).toEqual({ provider: "minimax", model: "MiniMax-M3" })
    })

    it("keeps MiniMax for unknown plan model names (legacy key-priority)", () => {
      expect(
        resolveModelForRole({
          DEEPSEEK_API_KEY: "ds-1",
          MINIMAX_API_KEY: "sk-mm",
          BUTLER_V5_MODEL_PLAN: "custom-alias",
          ...empty,
        }),
      ).toEqual({ provider: "minimax", model: "custom-alias" })
    })

    it("returns undefined when no provider configured", () => {
      expect(resolveModelForRole(empty)).toBeUndefined()
    })
  })

  describe("exec", () => {
    it("prefers MiniMax when MINIMAX_API_KEY set", () => {
      expect(resolveModelForRole({ MINIMAX_API_KEY: "sk-mm", ...empty }, "exec")).toEqual({
        provider: "minimax",
        model: "MiniMax-M3.1-Flash",
      })
    })

    it("honors BUTLER_V5_MODEL_EXEC for MiniMax", () => {
      expect(
        resolveModelForRole(
          { MINIMAX_API_KEY: "sk-mm", BUTLER_V5_MODEL_EXEC: "abab6.5", ...empty },
          "exec",
        ),
      ).toEqual({ provider: "minimax", model: "abab6.5" })
    })

    it("routes deepseek-name + deepseek key to DeepSeek (fix 400)", () => {
      expect(
        resolveModelForRole(
          {
            DEEPSEEK_API_KEY: "ds-1",
            MINIMAX_API_KEY: "sk-mm",
            BUTLER_V5_MODEL_EXEC: "deepseek-chat",
            ...empty,
          },
          "exec",
        ),
      ).toEqual({ provider: "deepseek", model: "deepseek-chat" })
    })

    it("falls back to plan when no exec provider configured", () => {
      expect(resolveModelForRole({ DEEPSEEK_API_KEY: "ds-1", ...empty }, "exec")).toEqual({
        provider: "deepseek",
        model: "deepseek-flash",
      })
    })
  })

  describe("intake", () => {
    it("prefers DeepSeek when DEEPSEEK_API_KEY set", () => {
      expect(resolveModelForRole({ DEEPSEEK_API_KEY: "ds-1", ...empty }, "intake")).toEqual({
        provider: "deepseek",
        model: "deepseek-flash",
      })
    })

    it("honors BUTLER_V5_MODEL_INTAKE then BUTLER_V5_MODEL_PLAN", () => {
      expect(
        resolveModelForRole(
          {
            DEEPSEEK_API_KEY: "ds-1",
            BUTLER_V5_MODEL_INTAKE: "intake-m",
            BUTLER_V5_MODEL_PLAN: "plan-m",
            ...empty,
          },
          "intake",
        ).model,
      ).toBe("intake-m")
      expect(
        resolveModelForRole(
          { DEEPSEEK_API_KEY: "ds-1", BUTLER_V5_MODEL_PLAN: "plan-m", ...empty },
          "intake",
        ).model,
      ).toBe("plan-m")
    })

    it("routes minimax-name intake model to MiniMax when both keys exist", () => {
      expect(
        resolveModelForRole(
          {
            DEEPSEEK_API_KEY: "ds-1",
            MINIMAX_API_KEY: "sk-mm",
            BUTLER_V5_MODEL_PLAN: "MiniMax-M3",
            ...empty,
          },
          "intake",
        ),
      ).toEqual({ provider: "minimax", model: "MiniMax-M3" })
    })

    it("routes deepseek-name intake model to DeepSeek when both keys exist", () => {
      expect(
        resolveModelForRole(
          {
            DEEPSEEK_API_KEY: "ds-1",
            MINIMAX_API_KEY: "sk-mm",
            BUTLER_V5_MODEL_INTAKE: "deepseek-v4-flash",
            ...empty,
          },
          "intake",
        ),
      ).toEqual({ provider: "deepseek", model: "deepseek-v4-flash" })
    })

    it("falls back to plan when no deepseek key", () => {
      expect(resolveModelForRole({ ANTHROPIC_API_KEY: "sk-1", ...empty }, "intake")).toEqual({
        provider: "anthropic",
        model: "claude-sonnet-4-20250514",
      })
    })
  })

  describe("isDeepSeekModelName", () => {
    it("detects deepseek model names case-insensitively", () => {
      expect(isDeepSeekModelName("deepseek-chat")).toBe(true)
      expect(isDeepSeekModelName("DeepSeek-V4-X")).toBe(true)
      expect(isDeepSeekModelName("MiniMax-M3")).toBe(false)
    })
  })
})
