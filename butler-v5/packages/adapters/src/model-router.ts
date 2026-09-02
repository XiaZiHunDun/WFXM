import { makeOpenAICompatibleAdapter } from "./llm/openai-compatible.js"
import { buildDeepSeekRequestExtras } from "./llm/deepseek-request.js"
import { makeAnthropicAdapter } from "./llm/anthropic.js"
import type { LLMAdapter } from "./llm-provider.js"
import { makeFixtureLLMAdapter, pickLLMFixtureDir } from "./llm-fixture.js"
import {
  isDeepSeekModelName,
  resolveModelForRole,
  type ResolvedModel,
} from "@butler/ports/core/model-port.js"

/** Model routing role: plan (main loop), exec (subagent/dev), intake (classification). */
export type ModelRole = "plan" | "exec" | "intake"

function envTrim(env: NodeJS.ProcessEnv, key: string): string {
  return (env[key] ?? "").trim()
}

function openAiCompatibleBaseUrl(raw: string): string {
  return raw.replace(/\/v1\/?$/, "").replace(/\/+$/, "")
}

/**
 * Build an LLMAdapter from a Model Port-resolved provider + model.
 * The resolver guarantees the matching API key is present, so we can
 * construct the adapter without re-checking availability.
 */
function buildAdapter(r: ResolvedModel, env: NodeJS.ProcessEnv): LLMAdapter {
  switch (r.provider) {
    case "anthropic":
      return makeAnthropicAdapter({ apiKey: envTrim(env, "ANTHROPIC_API_KEY"), model: r.model })
    case "deepseek": {
      const requestExtras = buildDeepSeekRequestExtras(env, r.model)
      return makeOpenAICompatibleAdapter({
        apiKey: envTrim(env, "DEEPSEEK_API_KEY"),
        baseUrl: "https://api.deepseek.com",
        model: r.model,
        ...(requestExtras !== undefined ? { requestExtras } : {}),
      })
    }
    case "minimax": {
      const cnKey = envTrim(env, "MINIMAX_CN_API_KEY")
      const intlKey = envTrim(env, "MINIMAX_API_KEY")
      const key = intlKey || cnKey
      const explicit =
        envTrim(env, "MINIMAX_BASE_URL") || envTrim(env, "BUTLER_WECHAT_MINIMAX_API_HOST")
      const defaultBase = cnKey && !intlKey ? "https://api.minimaxi.com" : "https://api.minimax.io"
      const baseUrl = openAiCompatibleBaseUrl(explicit || defaultBase)
      return makeOpenAICompatibleAdapter({ apiKey: key, baseUrl, model: r.model })
    }
    case "dashscope":
      return makeOpenAICompatibleAdapter({
        apiKey: envTrim(env, "DASHSCOPE_API_KEY"),
        baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
        model: r.model,
      })
  }
}

/**
 * Resolve the active provider + model for a role via the Model Port
 * (D44). Exposed so apps-api (e.g. llm-pricing accounting) can resolve
 * the same model the execution path uses — single source of truth.
 */
export function resolveLLMModel(
  env: NodeJS.ProcessEnv = process.env,
  role: ModelRole = "plan",
): ResolvedModel | undefined {
  return resolveModelForRole(env, role)
}

/**
 * Plan model: fast reasoning for main WeChat loop (default DeepSeek Flash).
 */
export function pickPlanLLM(env: NodeJS.ProcessEnv = process.env): LLMAdapter | undefined {
  const r = resolveModelForRole(env, "plan")
  return r ? buildAdapter(r, env) : undefined
}

/**
 * Exec model: code/tool-heavy subagent runs (default MiniMax M3).
 * Falls back to plan model when MiniMax is unavailable.
 */
export function execModelTrace(env: NodeJS.ProcessEnv = process.env): string {
  const model =
    envTrim(env, "BUTLER_V5_MODEL_EXEC") ||
    envTrim(env, "MINIMAX_MODEL") ||
    envTrim(env, "BUTLER_SMOKE_MINIMAX_MODEL") ||
    "MiniMax-M3"
  if (isDeepSeekModelName(model)) {
    if (envTrim(env, "DEEPSEEK_API_KEY")) return `exec:${model}`
    return "exec-fallback:plan"
  }
  const key = envTrim(env, "MINIMAX_API_KEY") || envTrim(env, "MINIMAX_CN_API_KEY")
  if (key) return `exec:${model}`
  return "exec-fallback:plan"
}

export function pickExecLLM(env: NodeJS.ProcessEnv = process.env): LLMAdapter | undefined {
  const r = resolveModelForRole(env, "exec")
  return r ? buildAdapter(r, env) : undefined
}

/**
 * Intake model: lightweight intent classification (default DeepSeek Flash).
 */
export function pickIntakeLLM(env: NodeJS.ProcessEnv = process.env): LLMAdapter | undefined {
  const r = resolveModelForRole(env, "intake")
  return r ? buildAdapter(r, env) : undefined
}

export function pickLLMForRole(
  env: NodeJS.ProcessEnv = process.env,
  role: ModelRole = "plan",
): LLMAdapter | undefined {
  const fixtureDir = pickLLMFixtureDir(env)
  if (fixtureDir) {
    return makeFixtureLLMAdapter({ fixtureDir, role })
  }
  switch (role) {
    case "exec":
      return pickExecLLM(env)
    case "intake":
      return pickIntakeLLM(env)
    case "plan":
    default:
      return pickPlanLLM(env)
  }
}