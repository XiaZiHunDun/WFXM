import { Effect, Stream } from "effect"
import type {
  LLMAssistantResponse,
  LLMMessage,
  LLMTool,
  LLMToolCall,
  LLMStopReason,
} from "../llm-provider.js"

interface OpenAICompatibleConfig {
  readonly apiKey: string
  readonly baseUrl: string
  readonly model?: string
  readonly fetch?: typeof fetch
  /** Merged into chat/completions JSON body (e.g. DeepSeek thinking toggle). */
  readonly requestExtras?: Readonly<Record<string, unknown>>
}

/**
 * OpenAI message in API request form. We extend the basic text shape
 * with `tool_calls` (for assistant messages that want to invoke tools)
 * and `tool_call_id` (for tool result messages — OpenAI's `role:"tool"`).
 */
interface OpenAIRequestMessage {
  readonly role: "user" | "assistant" | "system" | "tool"
  readonly content: string | null
  readonly tool_calls?: readonly OpenAIToolCallRequest[]
  readonly tool_call_id?: string
}

interface OpenAIToolCallRequest {
  readonly id: string
  readonly type: "function"
  readonly function: { readonly name: string; readonly arguments: string }
}

/**
 * OpenAI tool-call returned by the model. The `arguments` field is a
 * JSON string that the adapter parses into `args` on the provider-
 * agnostic `LLMToolCall`.
 */
interface OpenAIToolCallResponse {
  readonly id: string
  readonly type: "function"
  readonly function: { readonly name: string; readonly arguments: string }
}

interface OpenAIResponse {
  readonly choices: readonly {
    readonly message: {
      readonly role: string
      readonly content: string | null
      readonly tool_calls?: readonly OpenAIToolCallResponse[]
    }
    readonly finish_reason: string
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

/**
 * Convert provider-agnostic `LLMMessage`s into OpenAI's request shape.
 *   - assistant messages with toolCalls  → tool_calls field (stringified args)
 *   - role:"tool" messages                → tool_call_id field, content as the result
 *   - everything else                     → plain { role, content }
 */
function toOpenAIMessages(messages: readonly LLMMessage[]): readonly OpenAIRequestMessage[] {
  return messages.map((m) => {
    if (m.role === "tool") {
      return {
        role: "tool",
        content: m.content,
        tool_call_id: m.toolCallId ?? "",
      }
    }
    if (m.role === "assistant" && m.toolCalls && m.toolCalls.length > 0) {
      return {
        role: "assistant",
        content: m.content.length > 0 ? m.content : null,
        tool_calls: m.toolCalls.map((tc) => ({
          id: tc.id,
          type: "function" as const,
          function: {
            name: tc.name,
            arguments: JSON.stringify(tc.args),
          },
        })),
      }
    }
    return { role: m.role, content: m.content }
  })
}

/**
 * Parse OpenAI response into a provider-agnostic `LLMAssistantResponse`.
 * `arguments` on each tool_call is a JSON string — we parse it lazily
 * inside `tryParseArgs` so a malformed payload does not blow up the
 * whole response (we drop the call and log via the result instead).
 */
function parseOpenAIResponse(data: OpenAIResponse): LLMAssistantResponse {
  const choice = data.choices[0]
  if (!choice) {
    return { content: "", toolCalls: [], stopReason: "stop" }
  }
  const message = choice.message
  const content = message.content ?? ""
  const toolCalls: LLMToolCall[] = []
  const rawCalls = message.tool_calls ?? []
  for (const tc of rawCalls) {
    const args = tryParseArgs(tc.function.arguments)
    toolCalls.push({ id: tc.id, name: tc.function.name, args })
  }
  return {
    content,
    toolCalls,
    stopReason: mapStopReason(choice.finish_reason),
  }
}

/**
 * Parse the `arguments` JSON string on an OpenAI tool_call. If the
 * payload is malformed we return an empty object — the butler loop
 * will run the tool with no args and the tool's own validation can
 * surface the error if the missing arg matters.
 */
function tryParseArgs(raw: string): Record<string, unknown> {
  try {
    const parsed: unknown = JSON.parse(raw)
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>
    }
    return {}
  } catch {
    return {}
  }
}

function mapStopReason(reason: string): LLMStopReason {
  switch (reason) {
    case "stop":
      return "end_turn"
    case "tool_calls":
      return "tool_use"
    case "length":
      return "max_tokens"
    case "content_filter":
    default:
      return "stop"
  }
}

export function makeOpenAICompatibleAdapter(config: OpenAICompatibleConfig) {
  const model = config.model ?? "gpt-4o"
  const fetchImpl = config.fetch ?? fetch
  const requestExtras = config.requestExtras

  async function call(
    messages: readonly LLMMessage[],
    opts?: OpenAICallOptions,
  ): Promise<LLMAssistantResponse> {
    const body: Record<string, unknown> = {
      model,
      messages: toOpenAIMessages(messages),
      ...(requestExtras ?? {}),
    }
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
    if (!res.ok) {
      return Promise.reject(new Error(`openai api error: ${res.status}`))
    }
    const data = (await res.json()) as OpenAIResponse
    return parseOpenAIResponse(data)
  }

  return {
    complete: (messages: readonly LLMMessage[], opts?: OpenAICallOptions) =>
      Effect.tryPromise({
        try: () => call(messages, opts),
        catch: (err: unknown) => new Error(err instanceof Error ? err.message : String(err)),
      }),
    stream: (messages: readonly LLMMessage[], opts?: OpenAICallOptions) =>
      Stream.fromEffect(
        Effect.tryPromise({
          try: () => call(messages, opts),
          catch: (err: unknown) => new Error(err instanceof Error ? err.message : String(err)),
        }),
      ),
  }
}
