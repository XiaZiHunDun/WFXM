import { describe, expect, it, vi } from "vitest"
import { sendSlackOutboundMessage } from "./slack-outbound.js"

describe("sendSlackOutboundMessage", () => {
  it("posts chat.postMessage on success", async () => {
    const fetchMock = vi.fn(async () =>
      Response.json({ ok: true, ts: "123.456" }),
    )
    const result = await sendSlackOutboundMessage({
      token: "xoxb-test",
      channel: "C123",
      text: "hello slack",
      threadTs: "111.222",
      fetch: fetchMock as typeof fetch,
    })
    expect(result).toEqual({ ok: true })
    expect(fetchMock).toHaveBeenCalledWith(
      "https://slack.com/api/chat.postMessage",
      expect.objectContaining({ method: "POST" }),
    )
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit
    const body = JSON.parse(String(init.body)) as {
      channel: string
      text: string
      thread_ts: string
    }
    expect(body).toEqual({ channel: "C123", text: "hello slack", thread_ts: "111.222" })
  })

  it("omits thread_ts when not set", async () => {
    const fetchMock = vi.fn(async () => Response.json({ ok: true }))
    await sendSlackOutboundMessage({
      token: "xoxb",
      channel: "C1",
      text: "hi",
      fetch: fetchMock as typeof fetch,
    })
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit
    const body = JSON.parse(String(init.body)) as Record<string, unknown>
    expect("thread_ts" in body).toBe(false)
  })

  it("uses Bearer token in Authorization header", async () => {
    const fetchMock = vi.fn(async () => Response.json({ ok: true }))
    await sendSlackOutboundMessage({
      token: "xoxb-my-token",
      channel: "C1",
      text: "hi",
      fetch: fetchMock as typeof fetch,
    })
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit
    expect((init.headers as Record<string, string>).authorization).toBe("Bearer xoxb-my-token")
  })

  it("rejects empty token", async () => {
    const result = await sendSlackOutboundMessage({
      token: "",
      channel: "C1",
      text: "hi",
      fetch: vi.fn(),
    })
    expect(result).toEqual({ ok: false, reason: "slack bot token is required" })
  })

  it("rejects whitespace-only token", async () => {
    const result = await sendSlackOutboundMessage({
      token: "   ",
      channel: "C1",
      text: "hi",
      fetch: vi.fn(),
    })
    expect(result).toEqual({ ok: false, reason: "slack bot token is required" })
  })

  it("rejects empty channel", async () => {
    const result = await sendSlackOutboundMessage({
      token: "xoxb",
      channel: "",
      text: "hi",
      fetch: vi.fn(),
    })
    expect(result).toEqual({ ok: false, reason: "slack channel is required" })
  })

  it("rejects whitespace-only channel", async () => {
    const result = await sendSlackOutboundMessage({
      token: "xoxb",
      channel: "   ",
      text: "hi",
      fetch: vi.fn(),
    })
    expect(result).toEqual({ ok: false, reason: "slack channel is required" })
  })

  it("rejects empty text", async () => {
    const result = await sendSlackOutboundMessage({
      token: "xoxb",
      channel: "C1",
      text: "",
      fetch: vi.fn(),
    })
    expect(result).toEqual({ ok: false, reason: "reply is empty" })
  })

  it("rejects whitespace-only text", async () => {
    const result = await sendSlackOutboundMessage({
      token: "xoxb",
      channel: "C1",
      text: "   \n\t  ",
      fetch: vi.fn(),
    })
    expect(result).toEqual({ ok: false, reason: "reply is empty" })
  })

  it("clips text longer than 3900 chars with ellipsis", async () => {
    const fetchMock = vi.fn(async () => Response.json({ ok: true }))
    const longText = "a".repeat(5000)
    await sendSlackOutboundMessage({
      token: "xoxb",
      channel: "C1",
      text: longText,
      fetch: fetchMock as typeof fetch,
    })
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit
    const body = JSON.parse(String(init.body)) as { text: string }
    expect(body.text.length).toBe(3900)
    expect(body.text.endsWith("…")).toBe(true)
  })

  it("returns error on non-JSON response", async () => {
    const fetchMock = vi.fn(async () => new Response("not json", { status: 200 }))
    const result = await sendSlackOutboundMessage({
      token: "xoxb",
      channel: "C1",
      text: "hi",
      fetch: fetchMock as typeof fetch,
    })
    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(result.reason).toContain("slack API non-JSON")
  })

  it("returns error when API returns ok=false with error code", async () => {
    const fetchMock = vi.fn(async () =>
      Response.json({ ok: false, error: "channel_not_found" }),
    )
    const result = await sendSlackOutboundMessage({
      token: "xoxb",
      channel: "C1",
      text: "hi",
      fetch: fetchMock as typeof fetch,
    })
    expect(result).toEqual({ ok: false, reason: "channel_not_found" })
  })

  it("returns error on HTTP 500", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ ok: false, error: "server_error" }), { status: 500 }),
    )
    const result = await sendSlackOutboundMessage({
      token: "xoxb",
      channel: "C1",
      text: "hi",
      fetch: fetchMock as typeof fetch,
    })
    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(result.reason).toContain("server_error")
  })

  it("returns HTTP status error when API returns non-200 with ok=true", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ ok: true }), { status: 503 }),
    )
    const result = await sendSlackOutboundMessage({
      token: "xoxb",
      channel: "C1",
      text: "hi",
      fetch: fetchMock as typeof fetch,
    })
    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(result.reason).toContain("HTTP 503")
  })

  it("returns timeout error on AbortError", async () => {
    const fetchMock = vi.fn(async () => {
      const err = new Error("aborted")
      err.name = "AbortError"
      throw err
    })
    const result = await sendSlackOutboundMessage({
      token: "xoxb",
      channel: "C1",
      text: "hi",
      fetch: fetchMock as typeof fetch,
      timeoutMs: 100,
    })
    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(result.reason).toContain("slack API timeout")
    expect(result.reason).toContain("100ms")
  })

  it("returns error message on generic fetch failure", async () => {
    const fetchMock = vi.fn(async () => {
      throw new Error("ECONNREFUSED")
    })
    const result = await sendSlackOutboundMessage({
      token: "xoxb",
      channel: "C1",
      text: "hi",
      fetch: fetchMock as typeof fetch,
    })
    expect(result).toEqual({ ok: false, reason: "ECONNREFUSED" })
  })

  it("uses custom timeoutMs", async () => {
    const fetchMock = vi.fn(async () => Response.json({ ok: true }))
    await sendSlackOutboundMessage({
      token: "xoxb",
      channel: "C1",
      text: "hi",
      fetch: fetchMock as typeof fetch,
      timeoutMs: 5000,
    })
    // Just verify no crash; timeout value is internal AbortController config
    expect(fetchMock).toHaveBeenCalledOnce()
  })
})