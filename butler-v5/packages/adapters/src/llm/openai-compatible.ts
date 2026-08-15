import { Effect, Stream } from "effect"
import type { LLMTool } from "../llm-provider.js"

interface OpenAICompatibleConfig {
  readonly apiKey: string
  readonly baseUrl: string
  readonly model?: string
  readonly fetch?: typeof fetch
}

interface OpenAIMessage {
  readonly role: "user" | "assistant" | "system"
  readonly content: string
}

interface OpenAIResponse {
  readonly choices: readonly {
    readonly message: { readonly role: string; readonly content: string }
  }[]
}

/**
 * OpenAI-compatible tool definition as serialized into the chat
 * completions request body. The outer `type: "function"` envelope is
 * required by the OpenAI function-calling schema; parameters is a JSON
 * schema describing the tool's argument shape.
 */
export interface OpenAITool {
  readonly type: "function"
  readonly function: {
    readonly name: string
    readonly description: string
    readonly parameters: {
      readonly type: "object"
      readonly properties?: Record<string, unknown>
      readonly required?: readonly string[]
    }
  }
}

/**
 * Adapter accepts the provider-agnostic `LLMTool` shape (`parameters`)
 * and wraps it in the OpenAI `type: "function"` envelope. Keeps
 * callers free of provider knowledge.
 */
export interface OpenAICallOptions {
  readonly tools?: readonly LLMTool[]
}

function toOpenAITools(tools: readonly LLMTool[]): readonly OpenAITool[] {
  return tools.map((t) => {
    const params: {
      readonly type: "object"
      readonly properties?: Record<string, unknown>
      readonly required?: readonly string[]
    } = { type: "object", properties: t.parameters.properties ?? {} }
    if (t.parameters.required) {
      return {
        type: "function" as const,
        function: {
          name: t.name,
          description: t.description,
          parameters: { ...params, required: t.parameters.required },
        },
      }
    }
    return {
      type: "function" as const,
      function: {
        name: t.name,
        description: t.description,
        parameters: params,
      },
    }
  })
}

export function makeOpenAICompatibleAdapter(config: OpenAICompatibleConfig) {
  const model = config.model ?? "gpt-4o"
  const fetchImpl = config.fetch ?? fetch

  async function call(
    messages: readonly OpenAIMessage[],
    opts?: OpenAICallOptions,
  ): Promise<OpenAIMessage> {
    const body: Record<string, unknown> = { model, messages }
    const tools = opts?.tools
    if (tools && tools.length > 0) {
      body["tools"] = toOpenAITools(tools)
    }
    const res = await fetchImpl(`${config.baseUrl}/v1/chat/completions`, {
      method: "POST",
      headers: {
        authorization: `Bearer ${config.apiKey}`,
        "content-type": "application/json",
      },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error(`openai api error: ${res.status}`)
    const data = (await res.json()) as OpenAIResponse
    const m = data.choices[0]?.message
    return { role: "assistant", content: m?.content ?? "" }
  }

  return {
    complete: (
      messages: readonly { role: "user" | "assistant" | "system"; content: string }[],
      opts?: OpenAICallOptions,
    ) =>
      Effect.tryPromise({
        try: () => call(messages as readonly OpenAIMessage[], opts),
        catch: (err: unknown) => new Error(err instanceof Error ? err.message : String(err)),
      }),
    stream: (
      messages: readonly { role: "user" | "assistant" | "system"; content: string }[],
      opts?: OpenAICallOptions,
    ) =>
      Stream.fromEffect(
        Effect.tryPromise({
          try: () => call(messages as readonly OpenAIMessage[], opts),
          catch: (err: unknown) => new Error(err instanceof Error ? err.message : String(err)),
        }),
      ),
  }
}
