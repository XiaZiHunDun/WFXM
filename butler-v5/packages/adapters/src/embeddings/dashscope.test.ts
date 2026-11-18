import { describe, expect, it } from "vitest"
import { dashScopeEmbeddingFromEnv, makeDashScopeEmbeddingProvider } from "./dashscope.js"

describe("dashscope embeddings", () => {
  it("batches, sends dimensions, and orders rows by index", async () => {
    const calls: { url: string; body: Record<string, unknown>; auth: string }[] = []
    const fetchImpl = (async (url: string, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body)) as {
        input: string[]
        dimensions: number
      }
      calls.push({
        url: String(url),
        body,
        auth: String((init?.headers as Record<string, string>)["authorization"]),
      })
      const rows = body.input.map((_text, index) => ({
        index,
        embedding: [body.input.length, index],
      }))
      return new Response(JSON.stringify({ data: [...rows].reverse() }), { status: 200 })
    }) as unknown as typeof fetch

    const provider = makeDashScopeEmbeddingProvider({
      apiKey: "test-key",
      baseUrl: "http://example.test/v1",
      dimensions: 8,
      batchSize: 2,
      fetch: fetchImpl,
    })
    const vectors = await provider.embed(["a", "b", "c"])

    expect(vectors).toEqual([
      [2, 0],
      [2, 1],
      [1, 0],
    ])
    expect(calls).toHaveLength(2)
    expect(calls[0]?.url).toBe("http://example.test/v1/embeddings")
    expect(calls[0]?.auth).toBe("Bearer test-key")
    expect(calls[0]?.body["dimensions"]).toBe(8)
  })

  it("rejects non-2xx responses", async () => {
    const fetchImpl = (async () => new Response("no", { status: 401 })) as unknown as typeof fetch
    const provider = makeDashScopeEmbeddingProvider({ apiKey: "k", fetch: fetchImpl })
    await expect(provider.embed(["a"])).rejects.toThrow("embedding api error: 401")
  })

  it("resolves from env only when a key is present", () => {
    expect(dashScopeEmbeddingFromEnv({})).toBeNull()
    expect(
      dashScopeEmbeddingFromEnv({
        DASHSCOPE_API_KEY: "k",
        BUTLER_V5_EMBEDDING_ENABLED: "0",
      }),
    ).toBeNull()

    const provider = dashScopeEmbeddingFromEnv({ DASHSCOPE_API_KEY: "k" })
    expect(provider?.model).toBe("text-embedding-v3")
    expect(provider?.dimensions).toBe(1024)
  })
})
