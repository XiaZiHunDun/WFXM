/**
 * LLM pricing — D24 costUsd 闭环 (2026-08-31).
 *
 * Closes the D23 "costUsd reserved for future pricing batch" gap by
 * reading model-specific per-million-token USD prices from env vars and
 * computing per-call `costUsd` from `LLMAssistantResponse.usage`.
 *
 * Pricing env var format:
 *   BUTLER_V5_PRICING_<MODEL>_INPUT_PER_MTOK=3
 *   BUTLER_V5_PRICING_<MODEL>_OUTPUT_PER_MTOK=15
 *
 * where `<MODEL>` is the model identifier uppercased with `-`
 * replaced by `_`. Example: model `claude-sonnet-4-20250514`
 * becomes `BUTLER_V5_PRICING_CLAUDE_SONNET_4_20250514_INPUT_PER_MTOK`.
 *
 * Per §1.1 seam (delivery shell is apps/api + Core 薄编排层),
 * pricing lives in apps/api: runtime / adapters stay free of pricing
 * concerns. The 3 ports.complete callers (`wechat-inbound-butler` /
 * `subagent-worker` / `approval-resume`) look up pricing here and
 * pass `costUsd` into the `step/llm_call` trace event (D23).
 *
 * Missing pricing for a model = `null` (D24 decision: align with D23
 * costUsd null semantics; downstream distinguishes "unknown" from
 * "known free"). Not 0; not throw; trace emit must never break a run.
 */
import { resolveModelForRole } from "@butler/ports/core/model-port.js"

export interface ModelPricing {
  readonly inputPriceUsdPerMTok: number
  readonly outputPriceUsdPerMTok: number
}

/** Prefix every pricing env var shares. */
const PRICING_ENV_PREFIX = "BUTLER_V5_PRICING_"
const OUTPUT_SUFFIX = "_OUTPUT_PER_MTOK"

function modelKeyFromEnv(envKey: string): string | undefined {
  const match = envKey.match(/^BUTLER_V5_PRICING_(.+)_INPUT_PER_MTOK$/)
  if (!match) return undefined
  return match[1]
}

function envModelToLookupName(modelUpper: string): string {
  // `claude-sonnet-4-20250514` (env: `CLAUDE_SONNET_4_20250514`) → same.
  return modelUpper.toLowerCase().replace(/_/g, "-")
}

/**
 * Parse `BUTLER_V5_PRICING_<MODEL>_INPUT_PER_MTOK` +
 * `BUTLER_V5_PRICING_<MODEL>_OUTPUT_PER_MTOK` env vars into a map of
 * model name → pricing. Models missing either env var are simply
 * absent from the map (no entry). Non-numeric values are silently
 * skipped — pricing is best-effort observability, never blocks a run.
 */
export function parseLlmPricing(
  env: Readonly<NodeJS.ProcessEnv> = process.env,
): ReadonlyMap<string, ModelPricing> {
  const out = new Map<string, ModelPricing>()
  for (const envKey of Object.keys(env)) {
    const modelUpper = modelKeyFromEnv(envKey)
    if (modelUpper === undefined) continue
    const inputRaw = env[envKey]
    const outputRaw = env[`${PRICING_ENV_PREFIX}${modelUpper}${OUTPUT_SUFFIX}`]
    if (inputRaw === undefined || outputRaw === undefined) continue
    const input = Number(inputRaw)
    const output = Number(outputRaw)
    if (!Number.isFinite(input) || !Number.isFinite(output)) continue
    const lookupName = envModelToLookupName(modelUpper)
    out.set(lookupName, {
      inputPriceUsdPerMTok: input,
      outputPriceUsdPerMTok: output,
    })
  }
  return out
}

/**
 * Compute USD cost for one LLM call. Returns `null` when pricing for
 * `model` is not in the map (D24 decision: missing = null, not 0).
 *
 * Cost = (inputTokens × inputPricePerMTok + outputTokens ×
 * outputPricePerMTok) / 1_000_000. The 1M-token denominator matches
 * the env var units so the env values are directly the per-million
 * USD price.
 */
export function computeCostUsd(
  usage: { readonly inputTokens: number; readonly outputTokens: number },
  model: string,
  pricing: ReadonlyMap<string, ModelPricing>,
): number | null {
  const p = pricing.get(model)
  if (p === undefined) return null
  const cost =
    (usage.inputTokens / 1_000_000) * p.inputPriceUsdPerMTok +
    (usage.outputTokens / 1_000_000) * p.outputPriceUsdPerMTok
  return cost
}

/**
 * Resolve the current LLM model name from env for pricing lookup.
 *
 * D44 (P5 Model Port): the active model comes from the SAME Model Port
 * resolution the execution path uses (`resolveModelForRole(env, "plan")`),
 * so accounting keys off the real routing — no more "mirrors
 * pickLLMProvider" drift (the previous implementation omitted MiniMax
 * and the `BUTLER_V5_MODEL_*` overrides). Returns `null` when no
 * provider env var is set (caller falls back to costUsd: null).
 */
export function resolveCurrentLlmModel(
  env: Readonly<NodeJS.ProcessEnv> = process.env,
): string | null {
  return resolveModelForRole(env, "plan")?.model ?? null
}