import type { Effect } from "effect"
import { makeAnthropicAdapter } from "./llm/anthropic.js"
import { makeOpenAICompatibleAdapter } from "./llm/openai-compatible.js"
import { buildDeepSeekRequestExtras } from "./llm/deepseek-request.js"

/**
 * Minimal LLM message shape shared by all adapters.
 *
 * R8.x.4: extended with optional tool-call fields so the butler loop can
 * echo back assistant messages that contain native tool calls and feed
 * tool results back into the conversation. Providers serialize these
 * fields into the format each API expects:
 *   - Anthropic: assistant.toolCalls → content: [{type:"tool_use", ...}];
 *     role:"tool" → user message with content: [{type:"tool_result", ...}]
 *   - OpenAI-compatible: assistant.toolCalls → top-level tool_calls field;
 *     role:"tool" → top-level tool_call_id field
 */
export interface LLMMessage {
  readonly role: "user" | "assistant" | "system" | "tool"
  readonly content: string
  /**
   * For assistant messages: the tool calls the model wanted to make
   * (echoed back so the model sees its own tool_use in the next turn).
   * Adapter-specific: Anthropic serializes into tool_use blocks;
   * OpenAI-compatible serializes into tool_calls field.
   */
  readonly toolCalls?: readonly LLMToolCall[]
  /**
   * For tool result messages (role="tool"): links the result back to the
   * tool call that produced it. Required by OpenAI; ignored by Anthropic
   * (which uses the assistant.toolCalls position to associate results).
   */
  readonly toolCallId?: string
  /**
   * For tool result messages: the name of the tool that produced the
   * result. Anthropic tool_result blocks require the tool name.
   * OpenAI ignores it.
   */
  readonly toolName?: string
}

/**
 * Provider-agnostic tool descriptor passed to the adapter. Each
 * adapter serializes this into the format its API expects:
 *   - Anthropic: top-level `tools: [{ name, description, input_schema }]`
 *   - OpenAI-compatible: top-level `tools: [{ type: "function", function: {...} }]`
 *
 * The shape is intentionally narrow — the butler loop needs name +
 * description + parameter JSON schema, nothing more.
 */
export interface LLMTool {
  readonly name: string
  readonly description: string
  readonly parameters: {
    readonly type: "object"
    readonly properties?: Record<string, unknown>
    readonly required?: readonly string[]
  }
}

/**
 * Provider-agnostic tool call: the model wants to invoke `name` with
 * `args` (parsed from provider-specific response). `id` lets the butler
 * loop pair each result with its originating call so the model sees a
 * clean back-reference on the next turn.
 */
export interface LLMToolCall {
  readonly id: string
  readonly name: string
  readonly args: Record<string, unknown>
}

/**
 * Provider-agnostic stop reason. Normalized across Anthropic and
 * OpenAI-compatible so the butler loop can dispatch on a single union:
 *   - "end_turn" / "tool_use" — Anthropic native values
 *   - "stop" / "max_tokens"   — generic fallbacks (OpenAI "stop", "length",
 *                                "content_filter", or anything else)
 */
export type LLMStopReason = "end_turn" | "tool_use" | "max_tokens" | "stop"

/**
 * Rich assistant response shape returned by `LLMAdapter.complete`.
 *
 * R8.x.4: replaces the previous plain `LLMMessage` return so adapters
 * surface native tool_calls to the butler loop without parsing JSON out
 * of the model's text. `content` carries any text the model emitted
 * alongside tool calls (often empty when the model called a tool);
 * `toolCalls` is non-empty only when the model wanted to invoke one or
 * more tools.
 */
export interface LLMAssistantResponse {
  readonly content: string
  readonly toolCalls: readonly LLMToolCall[]
  readonly stopReason: LLMStopReason
}

/**
 * Minimal LLM adapter interface. `complete` accepts an optional
 * `tools` array; the butler loop (R8.x.3) passes the wechat tool set
 * so the model can decide whether to call a tool or reply directly.
 *
 * R8.x.4: the return is now `LLMAssistantResponse` (content + tool
 * calls + stop reason) so the butler loop can handle native tool_calls
 * without parsing JSON. `stream` is left out of scope until the async
 * butler loop lands.
 */
export interface LLMAdapter {
  readonly complete: (
    messages: readonly LLMMessage[],
    opts?: { readonly tools?: readonly LLMTool[] },
  ) => Effect.Effect<LLMAssistantResponse, Error>
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
    const model = env["DEEPSEEK_MODEL"] ?? "deepseek-chat"
    const requestExtras = buildDeepSeekRequestExtras(env, model)
    return makeOpenAICompatibleAdapter({
      apiKey: deepseekKey,
      baseUrl: "https://api.deepseek.com",
      model,
      ...(requestExtras !== undefined ? { requestExtras } : {}),
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
