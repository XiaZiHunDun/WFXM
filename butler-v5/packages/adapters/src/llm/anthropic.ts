import { Effect, Stream } from "effect"

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

export function makeAnthropicAdapter(config: AnthropicConfig) {
  const model = config.model ?? "claude-sonnet-4-20250514"
  const baseUrl = config.baseUrl ?? "https://api.anthropic.com"
  const fetchImpl = config.fetch ?? fetch

  async function call(messages: readonly AnthropicMessage[]): Promise<AnthropicMessage> {
    const res = await fetchImpl(`${baseUrl}/v1/messages`, {
      method: "POST",
      headers: {
        "x-api-key": config.apiKey,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
      },
      body: JSON.stringify({ model, max_tokens: 4096, messages }),
    })
    if (!res.ok) throw new Error(`anthropic api error: ${res.status}`)
    const data = (await res.json()) as AnthropicResponse
    const text = data.content[0]?.text ?? ""
    return { role: "assistant", content: text }
  }

  return {
    complete: (messages: readonly { role: "user" | "assistant" | "system"; content: string }[]) =>
      Effect.tryPromise({
        try: () => call(messages as readonly AnthropicMessage[]),
        catch: (err: unknown) => new Error(err instanceof Error ? err.message : String(err)),
      }),
    stream: (messages: readonly { role: "user" | "assistant" | "system"; content: string }[]) =>
      Stream.fromEffect(
        Effect.tryPromise({
          try: () => call(messages as readonly AnthropicMessage[]),
          catch: (err: unknown) => new Error(err instanceof Error ? err.message : String(err)),
        }),
      ),
  }
}
