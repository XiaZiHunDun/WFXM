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

  it("anthropic complete returns assistant content (text-only response)", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            content: [{ type: "text", text: "hello" }],
            stop_reason: "end_turn",
          }),
          { status: 200 },
        ),
    )
    const adapter = makeAnthropicAdapter({
      apiKey: "k",
      fetch: fetchMock as unknown as typeof fetch,
    })
    const result = await Effect.runPromise(adapter.complete([{ role: "user", content: "hi" }]))
    expect(result).toMatchObject({ content: "hello", toolCalls: [], stopReason: "end_turn" })
    expect(fetchMock).toHaveBeenCalled()
  })

  it("anthropic complete parses tool_use blocks into LLMToolCall[]", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            content: [
              {
                type: "tool_use",
                id: "tu_1",
                name: "get_current_time",
                input: { tz: "UTC" },
              },
            ],
            stop_reason: "tool_use",
          }),
          { status: 200 },
        ),
    )
    const adapter = makeAnthropicAdapter({
      apiKey: "k",
      fetch: fetchMock as unknown as typeof fetch,
    })
    const result = await Effect.runPromise(
      adapter.complete([{ role: "user", content: "what time?" }], {
        tools: [
          {
            name: "get_current_time",
            description: "Get current time",
            parameters: { type: "object", properties: { tz: { type: "string" } } },
          },
        ],
      }),
    )
    expect(result.content).toBe("")
    expect(result.stopReason).toBe("tool_use")
    expect(result.toolCalls).toEqual([
      { id: "tu_1", name: "get_current_time", args: { tz: "UTC" } },
    ])
  })

  it("anthropic complete joins multiple text blocks and surfaces mixed tool_use", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            content: [
              { type: "text", text: "let me check — " },
              { type: "tool_use", id: "tu_a", name: "recall_history", input: { limit: 3 } },
              { type: "text", text: "I'll use recall" },
            ],
            stop_reason: "tool_use",
          }),
          { status: 200 },
        ),
    )
    const adapter = makeAnthropicAdapter({
      apiKey: "k",
      fetch: fetchMock as unknown as typeof fetch,
    })
    const result = await Effect.runPromise(adapter.complete([{ role: "user", content: "?" }]))
    expect(result.content).toBe("let me check — I'll use recall")
    expect(result.toolCalls).toHaveLength(1)
    expect(result.toolCalls[0]?.name).toBe("recall_history")
  })

  it("anthropic complete normalizes unknown stop_reason to 'stop'", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify({ content: [{ type: "text", text: "x" }], stop_reason: "refusal" }),
          { status: 200 },
        ),
    )
    const adapter = makeAnthropicAdapter({
      apiKey: "k",
      fetch: fetchMock as unknown as typeof fetch,
    })
    const result = await Effect.runPromise(adapter.complete([{ role: "user", content: "?" }]))
    expect(result.stopReason).toBe("stop")
  })

  it("anthropic complete echoes assistant.toolCalls back as tool_use blocks", async () => {
    let capturedBody: Record<string, unknown> = {}
    const fetchMock = vi.fn(async (_url: unknown, init: unknown) => {
      capturedBody = JSON.parse((init as { body: string }).body) as Record<string, unknown>
      return new Response(
        JSON.stringify({ content: [{ type: "text", text: "ok" }], stop_reason: "end_turn" }),
        { status: 200 },
      )
    })
    const adapter = makeAnthropicAdapter({
      apiKey: "k",
      fetch: fetchMock as unknown as typeof fetch,
    })
    await Effect.runPromise(
      adapter.complete([
        { role: "user", content: "what time?" },
        {
          role: "assistant",
          content: "",
          toolCalls: [{ id: "tu_1", name: "get_current_time", args: {} }],
        },
        { role: "tool", content: "2026-08-15T00:00:00Z", toolCallId: "tu_1" },
      ]),
    )
    const sent = capturedBody["messages"] as {
      role: string
      content: unknown
    }[]
    expect(sent).toHaveLength(3)
    // assistant with toolCalls → assistant message with content blocks
    expect(sent[1]?.role).toBe("assistant")
    const assistantContent = sent[1]?.content as { type: string; name?: string; id?: string }[]
    expect(assistantContent).toHaveLength(1)
    expect(assistantContent[0]?.type).toBe("tool_use")
    expect(assistantContent[0]?.id).toBe("tu_1")
    expect(assistantContent[0]?.name).toBe("get_current_time")
    // role:tool → user message with tool_result block
    expect(sent[2]?.role).toBe("user")
    const userContent = sent[2]?.content as { type: string; tool_use_id?: string }[]
    expect(userContent[0]?.type).toBe("tool_result")
    expect(userContent[0]?.tool_use_id).toBe("tu_1")
  })

  it("openai complete returns assistant content (text-only response)", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            choices: [{ message: { role: "assistant", content: "hello" }, finish_reason: "stop" }],
          }),
          { status: 200 },
        ),
    )
    const adapter = makeOpenAICompatibleAdapter({
      apiKey: "k",
      baseUrl: "https://api.example.com",
      fetch: fetchMock as unknown as typeof fetch,
    })
    const result = await Effect.runPromise(adapter.complete([{ role: "user", content: "hi" }]))
    expect(result).toMatchObject({ content: "hello", toolCalls: [], stopReason: "end_turn" })
  })

  it("openai complete parses tool_calls into LLMToolCall[] with parsed JSON args", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            choices: [
              {
                message: {
                  role: "assistant",
                  content: null,
                  tool_calls: [
                    {
                      id: "tc_1",
                      type: "function",
                      function: {
                        name: "recall_history",
                        arguments: '{"limit":5}',
                      },
                    },
                  ],
                },
                finish_reason: "tool_calls",
              },
            ],
          }),
          { status: 200 },
        ),
    )
    const adapter = makeOpenAICompatibleAdapter({
      apiKey: "k",
      baseUrl: "https://api.example.com",
      fetch: fetchMock as unknown as typeof fetch,
    })
    const result = await Effect.runPromise(adapter.complete([{ role: "user", content: "?" }]))
    expect(result.content).toBe("")
    expect(result.stopReason).toBe("tool_use")
    expect(result.toolCalls).toEqual([{ id: "tc_1", name: "recall_history", args: { limit: 5 } }])
  })

  it("openai complete maps finish_reason 'length' to 'max_tokens'", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            choices: [{ message: { role: "assistant", content: "..." }, finish_reason: "length" }],
          }),
          { status: 200 },
        ),
    )
    const adapter = makeOpenAICompatibleAdapter({
      apiKey: "k",
      baseUrl: "https://api.example.com",
      fetch: fetchMock as unknown as typeof fetch,
    })
    const result = await Effect.runPromise(adapter.complete([{ role: "user", content: "?" }]))
    expect(result.stopReason).toBe("max_tokens")
  })

  it("openai complete falls back to empty args when arguments JSON is malformed", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            choices: [
              {
                message: {
                  role: "assistant",
                  content: null,
                  tool_calls: [
                    {
                      id: "tc_bad",
                      type: "function",
                      function: { name: "broken_tool", arguments: "not-json{" },
                    },
                  ],
                },
                finish_reason: "tool_calls",
              },
            ],
          }),
          { status: 200 },
        ),
    )
    const adapter = makeOpenAICompatibleAdapter({
      apiKey: "k",
      baseUrl: "https://api.example.com",
      fetch: fetchMock as unknown as typeof fetch,
    })
    const result = await Effect.runPromise(adapter.complete([{ role: "user", content: "?" }]))
    expect(result.toolCalls).toEqual([{ id: "tc_bad", name: "broken_tool", args: {} }])
  })

  it("openai complete echoes assistant.toolCalls back as tool_calls and role:tool as tool_call_id", async () => {
    let capturedBody: Record<string, unknown> = {}
    const fetchMock = vi.fn(async (_url: unknown, init: unknown) => {
      capturedBody = JSON.parse((init as { body: string }).body) as Record<string, unknown>
      return new Response(
        JSON.stringify({
          choices: [{ message: { role: "assistant", content: "ok" }, finish_reason: "stop" }],
        }),
        { status: 200 },
      )
    })
    const adapter = makeOpenAICompatibleAdapter({
      apiKey: "k",
      baseUrl: "https://api.example.com",
      fetch: fetchMock as unknown as typeof fetch,
    })
    await Effect.runPromise(
      adapter.complete([
        { role: "user", content: "what time?" },
        {
          role: "assistant",
          content: "",
          toolCalls: [{ id: "tc_1", name: "get_current_time", args: {} }],
        },
        { role: "tool", content: "2026-08-15T00:00:00Z", toolCallId: "tc_1" },
      ]),
    )
    const sent = capturedBody["messages"] as {
      role: string
      content?: unknown
      tool_calls?: unknown
      tool_call_id?: string
    }[]
    expect(sent).toHaveLength(3)
    expect(sent[1]?.role).toBe("assistant")
    expect(Array.isArray(sent[1]?.tool_calls)).toBe(true)
    expect(sent[2]?.role).toBe("tool")
    expect(sent[2]?.tool_call_id).toBe("tc_1")
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
      async () =>
        new Response(
          JSON.stringify({ content: [{ type: "text", text: "ok" }], stop_reason: "end_turn" }),
          { status: 200 },
        ),
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
    const tools = body["tools"] as Record<string, unknown>[]
    expect(tools).toHaveLength(1)
    expect(tools[0]).toMatchObject({
      name: "recall_history",
      description: "Read recent conversation history",
      input_schema: { type: "object" },
    })
  })

  it("anthropic complete omits tools field when none provided", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify({ content: [{ type: "text", text: "ok" }], stop_reason: "end_turn" }),
          { status: 200 },
        ),
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
          JSON.stringify({
            choices: [{ message: { role: "assistant", content: "ok" }, finish_reason: "stop" }],
          }),
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
    const tools = body["tools"] as Record<string, unknown>[]
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

  it("openai complete merges requestExtras into body", async () => {
    let capturedBody: Record<string, unknown> = {}
    const fetchMock = vi.fn(async (_url: unknown, init: unknown) => {
      capturedBody = JSON.parse((init as { body: string }).body) as Record<string, unknown>
      return new Response(
        JSON.stringify({
          choices: [{ message: { role: "assistant", content: "ok" }, finish_reason: "stop" }],
        }),
        { status: 200 },
      )
    })
    const adapter = makeOpenAICompatibleAdapter({
      apiKey: "k",
      baseUrl: "https://api.deepseek.com",
      model: "deepseek-v4-flash",
      requestExtras: { thinking: { type: "disabled" } },
      fetch: fetchMock as unknown as typeof fetch,
    })
    await Effect.runPromise(adapter.complete([{ role: "user", content: "hi" }]))
    expect(capturedBody["thinking"]).toEqual({ type: "disabled" })
  })

  it("openai complete omits tools field when none provided", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            choices: [{ message: { role: "assistant", content: "ok" }, finish_reason: "stop" }],
          }),
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

  // ── D23: usage parse for both adapters ──────────────────────

  it("anthropic complete surfaces upstream usage as LLMUsage (inputTokens + outputTokens + totalTokens)", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            content: [{ type: "text", text: "hi" }],
            stop_reason: "end_turn",
            usage: { input_tokens: 100, output_tokens: 50 },
          }),
          { status: 200 },
        ),
    )
    const adapter = makeAnthropicAdapter({
      apiKey: "k",
      fetch: fetchMock as unknown as typeof fetch,
    })
    const result = await Effect.runPromise(adapter.complete([{ role: "user", content: "hi" }]))
    expect(result.usage).toEqual({
      inputTokens: 100,
      outputTokens: 50,
      totalTokens: 150,
    })
  })

  it("anthropic complete leaves usage undefined when upstream omits it", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            content: [{ type: "text", text: "hi" }],
            stop_reason: "end_turn",
          }),
          { status: 200 },
        ),
    )
    const adapter = makeAnthropicAdapter({
      apiKey: "k",
      fetch: fetchMock as unknown as typeof fetch,
    })
    const result = await Effect.runPromise(adapter.complete([{ role: "user", content: "hi" }]))
    expect(result.usage).toBeUndefined()
  })

  it("openai-compatible complete surfaces upstream usage as LLMUsage (prompt + completion + total)", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            choices: [{ message: { role: "assistant", content: "ok" }, finish_reason: "stop" }],
            usage: { prompt_tokens: 200, completion_tokens: 80, total_tokens: 280 },
          }),
          { status: 200 },
        ),
    )
    const adapter = makeOpenAICompatibleAdapter({
      apiKey: "k",
      baseUrl: "https://api.example.com",
      fetch: fetchMock as unknown as typeof fetch,
    })
    const result = await Effect.runPromise(adapter.complete([{ role: "user", content: "hi" }]))
    expect(result.usage).toEqual({
      inputTokens: 200,
      outputTokens: 80,
      totalTokens: 280,
    })
  })

  it("openai-compatible complete leaves usage undefined when upstream omits it", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            choices: [{ message: { role: "assistant", content: "ok" }, finish_reason: "stop" }],
          }),
          { status: 200 },
        ),
    )
    const adapter = makeOpenAICompatibleAdapter({
      apiKey: "k",
      baseUrl: "https://api.example.com",
      fetch: fetchMock as unknown as typeof fetch,
    })
    const result = await Effect.runPromise(adapter.complete([{ role: "user", content: "hi" }]))
    expect(result.usage).toBeUndefined()
  })
})
