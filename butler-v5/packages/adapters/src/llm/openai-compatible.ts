import { Effect, Stream } from "effect"

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

export function makeOpenAICompatibleAdapter(config: OpenAICompatibleConfig) {
  const model = config.model ?? "gpt-4o"
  const fetchImpl = config.fetch ?? fetch

  async function call(messages: readonly OpenAIMessage[]): Promise<OpenAIMessage> {
    const res = await fetchImpl(`${config.baseUrl}/v1/chat/completions`, {
      method: "POST",
      headers: {
        authorization: `Bearer ${config.apiKey}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({ model, messages }),
    })
    if (!res.ok) throw new Error(`openai api error: ${res.status}`)
    const data = (await res.json()) as OpenAIResponse
    const m = data.choices[0]?.message
    return { role: "assistant", content: m?.content ?? "" }
  }

  return {
    complete: (messages: readonly { role: "user" | "assistant" | "system"; content: string }[]) =>
      Effect.tryPromise({
        try: () => call(messages as readonly OpenAIMessage[]),
        catch: (err: unknown) => new Error(err instanceof Error ? err.message : String(err)),
      }),
    stream: (messages: readonly { role: "user" | "assistant" | "system"; content: string }[]) =>
      Stream.fromEffect(
        Effect.tryPromise({
          try: () => call(messages as readonly OpenAIMessage[]),
          catch: (err: unknown) => new Error(err instanceof Error ? err.message : String(err)),
        }),
      ),
  }
}
