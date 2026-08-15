import { describe, expect, it, vi } from "vitest"
import { Effect } from "effect"
import { makeAnthropicAdapter } from "./anthropic.js"
import { makeOpenAICompatibleAdapter } from "./openai-compatible.js"

describe("LLM adapters", () => {
  it("anthropic adapter wires complete + stream", () => {
    const fetchMock = vi.fn(
      async () => new Response(JSON.stringify({ content: [{ text: "hi" }] }), { status: 200 }),
    )
    const live = makeAnthropicAdapter({ apiKey: "k", fetch: fetchMock as unknown as typeof fetch })
    const layer = { ...live }
    expect(layer.complete).toBeDefined()
    expect(typeof layer.complete).toBe("function")
    expect(typeof layer.stream).toBe("function")
  })

  it("openai compatible adapter wires complete + stream", () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(JSON.stringify({ choices: [{ message: { content: "hi" } }] }), {
          status: 200,
        }),
    )
    const live = makeOpenAICompatibleAdapter({
      apiKey: "k",
      baseUrl: "https://api.example.com",
      fetch: fetchMock as unknown as typeof fetch,
    })
    expect(live.complete).toBeDefined()
    expect(typeof live.stream).toBe("function")
  })

  it("anthropic complete returns message content", async () => {
    const fetchMock = vi.fn(
      async () => new Response(JSON.stringify({ content: [{ text: "hello" }] }), { status: 200 }),
    )
    const adapter = makeAnthropicAdapter({
      apiKey: "k",
      fetch: fetchMock as unknown as typeof fetch,
    })
    const result = await Effect.runPromise(adapter.complete([{ role: "user", content: "hi" }]))
    expect(result).toMatchObject({ role: "assistant", content: "hello" })
    expect(fetchMock).toHaveBeenCalled()
  })

  it("openai complete returns message content", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify({ choices: [{ message: { role: "assistant", content: "hello" } }] }),
          { status: 200 },
        ),
    )
    const adapter = makeOpenAICompatibleAdapter({
      apiKey: "k",
      baseUrl: "https://api.example.com",
      fetch: fetchMock as unknown as typeof fetch,
    })
    const result = await Effect.runPromise(adapter.complete([{ role: "user", content: "hi" }]))
    expect(result).toMatchObject({ role: "assistant", content: "hello" })
  })

  it("anthropic complete returns error when fetch fails", async () => {
    const fetchMock = vi.fn(async () => Promise.reject(new Error("network-down")))
    const adapter = makeAnthropicAdapter({
      apiKey: "k",
      fetch: fetchMock as unknown as typeof fetch,
    })
    await expect(
      Effect.runPromise(adapter.complete([{ role: "user", content: "hi" }])),
    ).rejects.toThrow(/network/i)
  })

  it("anthropic complete serializes tools in Anthropic format", async () => {
    const fetchMock = vi.fn(
      async () => new Response(JSON.stringify({ content: [{ text: "ok" }] }), { status: 200 }),
    )
    const adapter = makeAnthropicAdapter({
      apiKey: "k",
      fetch: fetchMock as unknown as typeof fetch,
    })
    await Effect.runPromise(
      adapter.complete([{ role: "user", content: "hi" }], {
        tools: [
          {
            name: "recall_history",
            description: "Read recent conversation history",
            parameters: { type: "object", properties: { limit: { type: "number" } } },
          },
        ],
      }),
    )
    const call = fetchMock.mock.calls[0]
    expect(call).toBeDefined()
    const body = JSON.parse((call?.[1] as { body: string }).body) as Record<string, unknown>
    expect(body["tools"]).toBeDefined()
    const tools = body["tools"] as Array<Record<string, unknown>>
    expect(tools).toHaveLength(1)
    expect(tools[0]).toMatchObject({
      name: "recall_history",
      description: "Read recent conversation history",
      input_schema: { type: "object" },
    })
  })

  it("anthropic complete omits tools field when none provided", async () => {
    const fetchMock = vi.fn(
      async () => new Response(JSON.stringify({ content: [{ text: "ok" }] }), { status: 200 }),
    )
    const adapter = makeAnthropicAdapter({
      apiKey: "k",
      fetch: fetchMock as unknown as typeof fetch,
    })
    await Effect.runPromise(adapter.complete([{ role: "user", content: "hi" }]))
    const call = fetchMock.mock.calls[0]
    const body = JSON.parse((call?.[1] as { body: string }).body) as Record<string, unknown>
    expect(body["tools"]).toBeUndefined()
  })

  it("openai complete serializes tools in OpenAI function-calling format", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify({ choices: [{ message: { role: "assistant", content: "ok" } }] }),
          { status: 200 },
        ),
    )
    const adapter = makeOpenAICompatibleAdapter({
      apiKey: "k",
      baseUrl: "https://api.example.com",
      fetch: fetchMock as unknown as typeof fetch,
    })
    await Effect.runPromise(
      adapter.complete([{ role: "user", content: "hi" }], {
        tools: [
          {
            name: "get_time",
            description: "Get current ISO time",
            parameters: { type: "object", properties: {} },
          },
        ],
      }),
    )
    const call = fetchMock.mock.calls[0]
    expect(call).toBeDefined()
    const body = JSON.parse((call?.[1] as { body: string }).body) as Record<string, unknown>
    expect(body["tools"]).toBeDefined()
    const tools = body["tools"] as Array<Record<string, unknown>>
    expect(tools).toHaveLength(1)
    expect(tools[0]).toMatchObject({
      type: "function",
      function: {
        name: "get_time",
        description: "Get current ISO time",
        parameters: { type: "object" },
      },
    })
  })

  it("openai complete omits tools field when none provided", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify({ choices: [{ message: { role: "assistant", content: "ok" } }] }),
          { status: 200 },
        ),
    )
    const adapter = makeOpenAICompatibleAdapter({
      apiKey: "k",
      baseUrl: "https://api.example.com",
      fetch: fetchMock as unknown as typeof fetch,
    })
    await Effect.runPromise(adapter.complete([{ role: "user", content: "hi" }]))
    const call = fetchMock.mock.calls[0]
    const body = JSON.parse((call?.[1] as { body: string }).body) as Record<string, unknown>
    expect(body["tools"]).toBeUndefined()
  })
})
