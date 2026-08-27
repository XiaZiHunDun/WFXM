import { makeOpenAICompatibleAdapter } from "./llm/openai-compatible.js"
import { buildDeepSeekRequestExtras } from "./llm/deepseek-request.js"
import { makeAnthropicAdapter } from "./llm/anthropic.js"
import { pickLLMProvider, type LLMAdapter } from "./llm-provider.js"
import { makeFixtureLLMAdapter, pickLLMFixtureDir } from "./llm-fixture.js"

/** Model routing role: plan (main loop), exec (subagent/dev), intake (classification). */
export type ModelRole = "plan" | "exec" | "intake"

function envTrim(env: NodeJS.ProcessEnv, key: string): string {
  return (env[key] ?? "").trim()
}

/** True for DeepSeek model ids（deepseek-chat / deepseek-v4-* 等），用于按模型名路由 provider。 */
function isDeepSeekModelName(model: string): boolean {
  return model.trim().toLowerCase().startsWith("deepseek")
}

function deepseekAdapter(env: NodeJS.ProcessEnv, model: string): LLMAdapter | undefined {
  const key = envTrim(env, "DEEPSEEK_API_KEY")
  if (!key) return undefined
  const requestExtras = buildDeepSeekRequestExtras(env, model)
  return makeOpenAICompatibleAdapter({
    apiKey: key,
    baseUrl: "https://api.deepseek.com",
    model,
    ...(requestExtras !== undefined ? { requestExtras } : {}),
  })
}

function openAiCompatibleBaseUrl(raw: string): string {
  return raw.replace(/\/v1\/?$/, "").replace(/\/+$/, "")
}

function minimaxAdapter(env: NodeJS.ProcessEnv, model: string): LLMAdapter | undefined {
  const cnKey = envTrim(env, "MINIMAX_CN_API_KEY")
  const intlKey = envTrim(env, "MINIMAX_API_KEY")
  const key = intlKey || cnKey
  if (!key) return undefined
  const explicit = envTrim(env, "MINIMAX_BASE_URL") || envTrim(env, "BUTLER_WECHAT_MINIMAX_API_HOST")
  const defaultBase = cnKey && !intlKey ? "https://api.minimaxi.com" : "https://api.minimax.io"
  const baseUrl = openAiCompatibleBaseUrl(explicit || defaultBase)
  return makeOpenAICompatibleAdapter({
    apiKey: key,
    baseUrl,
    model,
  })
}

/**
 * Plan model: fast reasoning for main WeChat loop (default DeepSeek Flash).
 */
export function pickPlanLLM(env: NodeJS.ProcessEnv = process.env): LLMAdapter | undefined {
  const anthropicKey = envTrim(env, "ANTHROPIC_API_KEY")
  if (anthropicKey) {
    return makeAnthropicAdapter({ apiKey: anthropicKey })
  }
  const model =
    envTrim(env, "BUTLER_V5_MODEL_PLAN") ||
    envTrim(env, "DEEPSEEK_MODEL") ||
    "deepseek-chat"
  const ds = deepseekAdapter(env, model)
  if (ds) return ds
  return pickLLMProvider(env)
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
  const model =
    envTrim(env, "BUTLER_V5_MODEL_EXEC") ||
    envTrim(env, "MINIMAX_MODEL") ||
    envTrim(env, "BUTLER_SMOKE_MINIMAX_MODEL") ||
    "MiniMax-M3"
  // BUTLER_V5_MODEL_EXEC 可能指定 deepseek 模型（如 deepseek-chat）：
  // 按模型名路由到 deepseek 通道，避免把 deepseek 模型名发给 MiniMax（400）。
  if (isDeepSeekModelName(model)) {
    const ds = deepseekAdapter(env, model)
    if (ds) return ds
  }
  const mm = minimaxAdapter(env, model)
  if (mm) return mm
  return pickPlanLLM(env)
}

/**
 * Intake model: lightweight intent classification (default DeepSeek Flash).
 */
export function pickIntakeLLM(env: NodeJS.ProcessEnv = process.env): LLMAdapter | undefined {
  const model =
    envTrim(env, "BUTLER_V5_MODEL_INTAKE") ||
    envTrim(env, "BUTLER_V5_MODEL_PLAN") ||
    envTrim(env, "DEEPSEEK_MODEL") ||
    "deepseek-chat"
  const ds = deepseekAdapter(env, model)
  if (ds) return ds
  return pickPlanLLM(env)
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
