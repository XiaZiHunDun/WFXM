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
})
