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
 *
 * ISSUE-02 (2026-11-12): env-var encoding cannot express model ids with
 * dots (`MiniMax-M3.1-Flash` → `MINIMAX_M3.1_FLASH`, not a legal shell
 * env name). A small built-in price table covers those ids; env vars
 * still override any entry whose name IS expressible.
 */
import { resolveModelForRole } from "@butler/ports/core/model-port.js"

export interface ModelPricing {
  readonly inputPriceUsdPerMTok: number
  readonly outputPriceUsdPerMTok: number
}

/**
 * Built-in prices (USD per 1M tokens) for model ids that env vars cannot
 * express. Sources checked 2026-11-12:
 * - `MiniMax-M3.1-Flash`: $0.15 input / $0.60 output (MiniMax pay-as-you-go
 *   pricing; cache read $0.015 is not modeled — usage has no cache split).
 * - DeepSeek Flash (legacy id `deepseek-v4-flash` is still accepted and
 *   billed as `deepseek-flash`): peak $0.30 input / $1.20 output; off-peak
 *   is half. Peak is used here so costs are not understated.
 */
const BUILTIN_PRICING: Readonly<Record<string, ModelPricing>> = {
  "minimax-m3.1-flash": { inputPriceUsdPerMTok: 0.15, outputPriceUsdPerMTok: 0.6 },
  "deepseek-flash": { inputPriceUsdPerMTok: 0.3, outputPriceUsdPerMTok: 1.2 },
  "deepseek-v4-flash": { inputPriceUsdPerMTok: 0.3, outputPriceUsdPerMTok: 1.2 },
  // Company private deployment (OpenAI-compatible, single served model).
  // Not billed per token, so internal cost is 0 rather than "unknown" (null).
  "deepseek-v4.1-flash": { inputPriceUsdPerMTok: 0, outputPriceUsdPerMTok: 0 },
}

/** Case-insensitive pricing key; model ids come from provider routing. */
function normalizeModelName(model: string): string {
  return model.trim().toLowerCase()
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
 * Resolve pricing for the current env: built-in table first, then
 * `BUTLER_V5_PRICING_<MODEL>_INPUT/OUTPUT_PER_MTOK` env vars override.
 *
 * Models missing either env var keep their built-in entry (if any);
 * env-only models missing a partner var stay absent. Non-numeric values
 * are silently skipped — pricing is best-effort observability, never
 * blocks a run.
 */
export function parseLlmPricing(
  env: Readonly<NodeJS.ProcessEnv> = process.env,
): ReadonlyMap<string, ModelPricing> {
  const out = new Map<string, ModelPricing>(Object.entries(BUILTIN_PRICING))
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
  const p = pricing.get(normalizeModelName(model))
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
 * so accounting keys off the real routing — no more "mirrors the
 * provider picker" drift (the previous implementation omitted MiniMax
 * and the `BUTLER_V5_MODEL_*` overrides). Returns `null` when no
 * provider env var is set (caller falls back to costUsd: null).
 * (D82 T3: named the deleted `pickLLMProvider`; the surviving name is
 * `resolveModelForRole`, as referenced above.)
 */
export function resolveCurrentLlmModel(
  env: Readonly<NodeJS.ProcessEnv> = process.env,
): string | null {
  return resolveModelForRole(env, "plan")?.model ?? null
}
