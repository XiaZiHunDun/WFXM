import { Effect, Stream } from "effect"
import type {
  LLMAssistantResponse,
  LLMMessage,
  LLMTool,
  LLMToolCall,
  LLMStopReason,
} from "../llm-provider.js"

interface AnthropicConfig {
  readonly apiKey: string
  readonly model?: string
  readonly baseUrl?: string
  readonly fetch?: typeof fetch
}

/**
 * Anthropic message in API request form. Anthropic's content field is a
 * list of typed blocks; we serialize provider-agnostic `LLMMessage`s
 * into this shape in `toAnthropicMessages`.
 */
interface AnthropicRequestMessage {
  readonly role: "user" | "assistant" | "system"
  readonly content: string | readonly AnthropicContentBlock[]
}

type AnthropicContentBlock =
  | { readonly type: "text"; readonly text: string }
  | {
      readonly type: "tool_use"
      readonly id: string
      readonly name: string
      readonly input: Record<string, unknown>
    }
  | { readonly type: "tool_result"; readonly tool_use_id: string; readonly content: string }
  | { readonly type: string; readonly [key: string]: unknown }

/**
 * Anthropic response shape. Content is a list of typed blocks; the
 * adapter parses text blocks into `content` and tool_use blocks into
 * `toolCalls`. Unknown block types are silently dropped (forward
 * compatibility for new Anthropic features). `usage` carries token
 * counts surfaced to the butler loop and forwarded to trace events
 * (D23); the field is optional because some upstream paths (mocked
 * fixtures, certain failure modes) may omit it.
 */
interface AnthropicResponse {
  readonly content: readonly AnthropicContentBlock[]
  readonly stop_reason: string
  readonly usage?: {
    readonly input_tokens: number
    readonly output_tokens: number
  }
}

/**
 * Anthropic tool definition as serialized into the Messages API request
 * body. Anthropic keeps tools as a top-level field (separate from
 * messages), so each tool needs a `name`, `description`, and an
 * `input_schema` describing its argument shape.
 */
export interface AnthropicTool {
  readonly name: string
  readonly description: string
  readonly input_schema: {
    readonly type: "object"
    readonly properties?: Record<string, unknown>
    readonly required?: readonly string[]
  }
}

/**
 * Adapter accepts the provider-agnostic `LLMTool` shape (`parameters`)
 * and translates it to the Anthropic-specific shape (`input_schema`).
 * Keeps callers free of provider knowledge.
 */
export interface AnthropicCallOptions {
  readonly tools?: readonly LLMTool[]
}

function toAnthropicTools(tools: readonly LLMTool[]): readonly AnthropicTool[] {
  return tools.map((t) => {
    const input_schema: {
      readonly type: "object"
      readonly properties?: Record<string, unknown>
      readonly required?: readonly string[]
    } = { type: "object", properties: t.parameters.properties ?? {} }
    if (t.parameters.required) {
      return {
        name: t.name,
        description: t.description,
        input_schema: { ...input_schema, required: t.parameters.required },
      }
    }
    return {
      name: t.name,
      description: t.description,
      input_schema,
    }
  })
}

/**
 * Convert provider-agnostic `LLMMessage`s into Anthropic's request shape.
 * The mapping handles three special cases:
 *   - role:"tool"           → user message with a tool_result block
 *   - assistant.toolCalls   → assistant message with tool_use blocks
 *                              (and an optional text block if content is non-empty)
 *   - everything else        → plain { role, content: string }
 */
function toAnthropicMessages(messages: readonly LLMMessage[]): readonly AnthropicRequestMessage[] {
  const out: AnthropicRequestMessage[] = []
  for (const m of messages) {
    if (m.role === "tool") {
      out.push({
        role: "user",
        content: [
          {
            type: "tool_result",
            tool_use_id: m.toolCallId ?? "",
            content: m.content,
          },
        ],
      })
      continue
    }
    if (m.role === "assistant" && m.toolCalls && m.toolCalls.length > 0) {
      const blocks: AnthropicContentBlock[] = []
      if (m.content.length > 0) {
        blocks.push({ type: "text", text: m.content })
      }
      for (const tc of m.toolCalls) {
        blocks.push({
          type: "tool_use",
          id: tc.id,
          name: tc.name,
          input: tc.args,
        })
      }
      out.push({ role: "assistant", content: blocks })
      continue
    }
    out.push({ role: m.role, content: m.content })
  }
  return out
}

/**
 * Parse Anthropic response content blocks into a provider-agnostic
 * `LLMAssistantResponse`. Text blocks join into `content`; tool_use
 * blocks become `toolCalls`. Other block types are ignored (forward
 * compatibility for new Anthropic content types). When `data.usage`
 * is present, surface it as `usage` (D23) so the caller can forward
 * it to trace events.
 */
function parseAnthropicResponse(data: AnthropicResponse): LLMAssistantResponse {
  const textParts: string[] = []
  const toolCalls: LLMToolCall[] = []
  for (const block of data.content) {
    if (block.type === "text") {
      const textBlock = block as { readonly type: "text"; readonly text: string }
      textParts.push(textBlock.text)
    } else if (block.type === "tool_use") {
      const toolBlock = block as {
        readonly type: "tool_use"
        readonly id: string
        readonly name: string
        readonly input: Record<string, unknown>
      }
      toolCalls.push({
        id: toolBlock.id,
        name: toolBlock.name,
        args: toolBlock.input,
      })
    }
    // Unknown block types are ignored on purpose.
  }
  const usage = data.usage
    ? {
        inputTokens: data.usage.input_tokens,
        outputTokens: data.usage.output_tokens,
        totalTokens: data.usage.input_tokens + data.usage.output_tokens,
      }
    : undefined
  return {
    content: textParts.join(""),
    toolCalls,
    stopReason: mapStopReason(data.stop_reason),
    ...(usage !== undefined ? { usage } : {}),
  }
}

function mapStopReason(reason: string): LLMStopReason {
  switch (reason) {
    case "end_turn":
      return "end_turn"
    case "tool_use":
      return "tool_use"
    case "max_tokens":
      return "max_tokens"
    default:
      return "stop"
  }
}

export function makeAnthropicAdapter(config: AnthropicConfig) {
  const model = config.model ?? "claude-sonnet-4-20250514"
  const baseUrl = config.baseUrl ?? "https://api.anthropic.com"
  const fetchImpl = config.fetch ?? fetch

  async function call(
    messages: readonly LLMMessage[],
    opts?: AnthropicCallOptions,
  ): Promise<LLMAssistantResponse> {
    const body: Record<string, unknown> = {
      model,
      max_tokens: 4096,
      messages: toAnthropicMessages(messages),
    }
    const tools = opts?.tools
    if (tools && tools.length > 0) {
      body["tools"] = toAnthropicTools(tools)
    }
    const res = await fetchImpl(`${baseUrl}/v1/messages`, {
      method: "POST",
      headers: {
        "x-api-key": config.apiKey,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
      },
      body: JSON.stringify(body),
    })
    if (!res.ok) {
      return Promise.reject(new Error(`anthropic api error: ${res.status}`))
    }
    const data = (await res.json()) as AnthropicResponse
    return parseAnthropicResponse(data)
  }

  return {
    complete: (messages: readonly LLMMessage[], opts?: AnthropicCallOptions) =>
      Effect.tryPromise({
        try: () => call(messages, opts),
        catch: (err: unknown) => new Error(err instanceof Error ? err.message : String(err)),
      }),
    stream: (messages: readonly LLMMessage[], opts?: AnthropicCallOptions) =>
      Stream.fromEffect(
        Effect.tryPromise({
          try: () => call(messages, opts),
          catch: (err: unknown) => new Error(err instanceof Error ? err.message : String(err)),
        }),
      ),
  }
}
