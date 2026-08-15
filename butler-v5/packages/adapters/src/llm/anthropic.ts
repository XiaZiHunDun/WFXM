import { Effect, Stream } from "effect"
import type { LLMTool } from "../llm-provider.js"

interface AnthropicConfig {
  readonly apiKey: string
  readonly model?: string
  readonly baseUrl?: string
  readonly fetch?: typeof fetch
}

interface AnthropicMessage {
  readonly role: "user" | "assistant" | "system"
  readonly content: string
}

interface AnthropicResponse {
  readonly content: readonly { readonly text: string }[]
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

export function makeAnthropicAdapter(config: AnthropicConfig) {
  const model = config.model ?? "claude-sonnet-4-20250514"
  const baseUrl = config.baseUrl ?? "https://api.anthropic.com"
  const fetchImpl = config.fetch ?? fetch

  async function call(
    messages: readonly AnthropicMessage[],
    opts?: AnthropicCallOptions,
  ): Promise<AnthropicMessage> {
    const body: Record<string, unknown> = { model, max_tokens: 4096, messages }
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
    if (!res.ok) throw new Error(`anthropic api error: ${res.status}`)
    const data = (await res.json()) as AnthropicResponse
    const text = data.content[0]?.text ?? ""
    return { role: "assistant", content: text }
  }

  return {
    complete: (
      messages: readonly { role: "user" | "assistant" | "system"; content: string }[],
      opts?: AnthropicCallOptions,
    ) =>
      Effect.tryPromise({
        try: () => call(messages as readonly AnthropicMessage[], opts),
        catch: (err: unknown) => new Error(err instanceof Error ? err.message : String(err)),
      }),
    stream: (
      messages: readonly { role: "user" | "assistant" | "system"; content: string }[],
      opts?: AnthropicCallOptions,
    ) =>
      Stream.fromEffect(
        Effect.tryPromise({
          try: () => call(messages as readonly AnthropicMessage[], opts),
          catch: (err: unknown) => new Error(err instanceof Error ? err.message : String(err)),
        }),
      ),
  }
}
