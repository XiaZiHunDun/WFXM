import { describe, expect, it } from "vitest"
import {
  computeCostUsd,
  parseLlmPricing,
  resolveCurrentLlmModel,
  type ModelPricing,
} from "./llm-pricing.js"

describe("llm-pricing (D24 costUsd 闭环)", () => {
  // ── parseLlmPricing ─────────────────────────────────────────

  describe("parseLlmPricing", () => {
    it("includes built-in pricing for ids env vars cannot express", () => {
      const map = parseLlmPricing({})
      expect(map.get("minimax-m3.1-flash")).toEqual({
        inputPriceUsdPerMTok: 0.15,
        outputPriceUsdPerMTok: 0.6,
      })
      expect(map.get("deepseek-flash")).toEqual({
        inputPriceUsdPerMTok: 0.3,
        outputPriceUsdPerMTok: 1.2,
      })
      expect(map.get("deepseek-v4-flash")).toEqual({
        inputPriceUsdPerMTok: 0.3,
        outputPriceUsdPerMTok: 1.2,
      })
    })

    it("parses one model with both input + output env vars", () => {
      const map = parseLlmPricing({
        BUTLER_V5_PRICING_CLAUDE_SONNET_4_20250514_INPUT_PER_MTOK: "3",
        BUTLER_V5_PRICING_CLAUDE_SONNET_4_20250514_OUTPUT_PER_MTOK: "15",
      })
      expect(map.get("claude-sonnet-4-20250514")).toEqual({
        inputPriceUsdPerMTok: 3,
        outputPriceUsdPerMTok: 15,
      })
      // Built-in entries survive alongside env-defined models.
      expect(map.has("minimax-m3.1-flash")).toBe(true)
    })

    it("parses multiple models independently", () => {
      const map = parseLlmPricing({
        BUTLER_V5_PRICING_CLAUDE_SONNET_4_20250514_INPUT_PER_MTOK: "3",
        BUTLER_V5_PRICING_CLAUDE_SONNET_4_20250514_OUTPUT_PER_MTOK: "15",
        BUTLER_V5_PRICING_DEEPSEEK_CHAT_INPUT_PER_MTOK: "0.27",
        BUTLER_V5_PRICING_DEEPSEEK_CHAT_OUTPUT_PER_MTOK: "1.1",
      })
      expect(map.get("claude-sonnet-4-20250514")?.inputPriceUsdPerMTok).toBe(3)
      expect(map.get("deepseek-chat")?.outputPriceUsdPerMTok).toBe(1.1)
    })

    it("lets env override a built-in entry whose name is expressible", () => {
      const map = parseLlmPricing({
        BUTLER_V5_PRICING_DEEPSEEK_FLASH_INPUT_PER_MTOK: "9",
        BUTLER_V5_PRICING_DEEPSEEK_FLASH_OUTPUT_PER_MTOK: "18",
      })
      expect(map.get("deepseek-flash")).toEqual({
        inputPriceUsdPerMTok: 9,
        outputPriceUsdPerMTok: 18,
      })
    })

    it("skips models that are missing the output env var", () => {
      const map = parseLlmPricing({
        BUTLER_V5_PRICING_CLAUDE_SONNET_4_20250514_INPUT_PER_MTOK: "3",
        // no OUTPUT_PER_MTOK partner
      })
      expect(map.has("claude-sonnet-4-20250514")).toBe(false)
    })

    it("skips models whose env values are not finite numbers", () => {
      const map = parseLlmPricing({
        BUTLER_V5_PRICING_FOO_INPUT_PER_MTOK: "abc",
        BUTLER_V5_PRICING_FOO_OUTPUT_PER_MTOK: "15",
      })
      expect(map.has("foo")).toBe(false)
    })

    it("ignores unrelated env vars", () => {
      const map = parseLlmPricing({
        BUTLER_V5_OTHER_THING: "value",
        ANTHROPIC_API_KEY: "sk-1234",
        BUTLER_V5_PRICING_GPT_4O_INPUT_PER_MTOK: "2.5",
        BUTLER_V5_PRICING_GPT_4O_OUTPUT_PER_MTOK: "10",
      })
      expect(map.has("gpt-4o")).toBe(true)
    })
  })

  // ── computeCostUsd ──────────────────────────────────────────

  describe("computeCostUsd", () => {
    const pricing: ReadonlyMap<string, ModelPricing> = new Map([
      ["claude-sonnet-4-20250514", { inputPriceUsdPerMTok: 3, outputPriceUsdPerMTok: 15 }],
    ])

    it("computes cost from inputTokens × inputPrice + outputTokens × outputPrice / 1M", () => {
      // 1M input @ $3 + 1M output @ $15 = $3 + $15 = $18
      const cost = computeCostUsd(
        { inputTokens: 1_000_000, outputTokens: 1_000_000 },
        "claude-sonnet-4-20250514",
        pricing,
      )
      expect(cost).toBe(18)
    })

    it("computes fractional cost for non-million token counts", () => {
      // 100k input @ $3 + 50k output @ $15 = $0.30 + $0.75 = $1.05
      const cost = computeCostUsd(
        { inputTokens: 100_000, outputTokens: 50_000 },
        "claude-sonnet-4-20250514",
        pricing,
      )
      expect(cost).toBeCloseTo(1.05, 10)
    })

    it("returns null when model is not in pricing map (D24: missing = null)", () => {
      const cost = computeCostUsd(
        { inputTokens: 1_000, outputTokens: 500 },
        "unknown-model",
        pricing,
      )
      expect(cost).toBeNull()
    })

    it("matches built-in dotted model ids case-insensitively", () => {
      // 1M input @ $0.15 + 1M output @ $0.60 = $0.75
      const cost = computeCostUsd(
        { inputTokens: 1_000_000, outputTokens: 1_000_000 },
        "MiniMax-M3.1-Flash",
        parseLlmPricing({}),
      )
      expect(cost).toBeCloseTo(0.75, 10)
    })

    it("returns 0 when both token counts are 0 and pricing is present", () => {
      const cost = computeCostUsd(
        { inputTokens: 0, outputTokens: 0 },
        "claude-sonnet-4-20250514",
        pricing,
      )
      expect(cost).toBe(0)
    })
  })

  // ── resolveCurrentLlmModel ──────────────────────────────────

  describe("resolveCurrentLlmModel", () => {
    it("returns Anthropic default when ANTHROPIC_API_KEY is set", () => {
      expect(resolveCurrentLlmModel({ ANTHROPIC_API_KEY: "sk-1234" })).toBe(
        "claude-sonnet-4-20250514",
      )
    })

    it("honors ANTHROPIC_MODEL override", () => {
      expect(
        resolveCurrentLlmModel({
          ANTHROPIC_API_KEY: "sk-1234",
          ANTHROPIC_MODEL: "claude-haiku-4-5-20251001",
        }),
      ).toBe("claude-haiku-4-5-20251001")
    })

    it("returns DeepSeek default when only DEEPSEEK_API_KEY is set", () => {
      expect(resolveCurrentLlmModel({ DEEPSEEK_API_KEY: "ds-1234" })).toBe("deepseek-flash")
    })

    it("returns DashScope default when only DASHSCOPE_API_KEY is set", () => {
      expect(resolveCurrentLlmModel({ DASHSCOPE_API_KEY: "dq-1234" })).toBe("qwen-turbo")
    })

    it("returns null when no provider env var is set", () => {
      expect(resolveCurrentLlmModel({})).toBeNull()
    })

    it("honors BUTLER_V5_MODEL_PLAN override (D44 Model Port routing)", () => {
      expect(
        resolveCurrentLlmModel({
          DEEPSEEK_API_KEY: "ds-1234",
          BUTLER_V5_MODEL_PLAN: "deepseek-v4-x",
        }),
      ).toBe("deepseek-v4-x")
    })

    it("defaults plan model to DeepSeek when both DEEPSEEK_API_KEY and MINIMAX_API_KEY are set", () => {
      // 2026-11-19 默认选型：两个 key 共存且未显式指定模型时，plan 默认
      // deepseek-flash（heldout 6/6、P95 28s vs MiniMax 5/6、P95 142s）。
      // 该断言与 BUTLER_V5_MODEL_EXEC 无关（此处设为 "abab6.5"，
      // 若 exec 角色串入 plan 会立即失败）。
      expect(
        resolveCurrentLlmModel({
          DEEPSEEK_API_KEY: "ds-1234",
          MINIMAX_API_KEY: "sk-mm",
          BUTLER_V5_MODEL_EXEC: "abab6.5",
        }),
      ).toBe("deepseek-flash")
    })
  })
})
