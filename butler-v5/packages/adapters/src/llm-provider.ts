import type { Effect } from "effect"
import { makeAnthropicAdapter } from "./llm/anthropic.js"
import { makeOpenAICompatibleAdapter } from "./llm/openai-compatible.js"

/**
 * Minimal LLM message shape shared by all adapters.
 * Adapters already accept this exact shape.
 */
export interface LLMMessage {
  readonly role: "user" | "assistant" | "system"
  readonly content: string
}

/**
 * Minimal LLM adapter interface — only `complete` is required for R8.x.2
 * (synchronous request/reply from /v1/wechat/inbound). `stream` is left
 * out of scope until the async butler loop lands in R8.x.3.
 */
export interface LLMAdapter {
  readonly complete: (messages: readonly LLMMessage[]) => Effect.Effect<LLMMessage, Error>
}

/**
 * Pick an LLM provider based on env vars (priority order):
 *   1. ANTHROPIC_API_KEY → Anthropic Messages API
 *   2. DEEPSEEK_API_KEY  → DeepSeek (OpenAI-compatible)
 *   3. DASHSCOPE_API_KEY → DashScope Qwen (OpenAI-compatible)
 *   4. none set          → undefined (caller falls back to stub reply)
 *
 * Pure function: takes env as an argument so tests can inject values
 * and so the deployment / runtime decides which env to pass.
 */
export function pickLLMProvider(env: NodeJS.ProcessEnv = process.env): LLMAdapter | undefined {
  const anthropicKey = env["ANTHROPIC_API_KEY"]
  if (anthropicKey) {
    return makeAnthropicAdapter({ apiKey: anthropicKey })
  }
  const deepseekKey = env["DEEPSEEK_API_KEY"]
  if (deepseekKey) {
    return makeOpenAICompatibleAdapter({
      apiKey: deepseekKey,
      baseUrl: "https://api.deepseek.com/v1",
      model: env["DEEPSEEK_MODEL"] ?? "deepseek-chat",
    })
  }
  const dashscopeKey = env["DASHSCOPE_API_KEY"]
  if (dashscopeKey) {
    return makeOpenAICompatibleAdapter({
      apiKey: dashscopeKey,
      baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
      model: "qwen-turbo",
    })
  }
  return undefined
}
