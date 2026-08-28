import { describe, expect, it, vi } from "vitest"
import { sendSlackOutboundFile } from "./slack-outbound-media.js"

describe("sendSlackOutboundFile", () => {
  it("uploads file via files.upload on success", async () => {
    const fetchMock = vi.fn(async () =>
      Response.json({ ok: true, file: { id: "F123" } }),
    )
    const result = await sendSlackOutboundFile({
      token: "xoxb-test",
      channel: "C123",
      filePath: "/tmp/report.pdf",
      fileName: "report.pdf",
      bytes: Buffer.from("pdf-content"),
      fetch: fetchMock as typeof fetch,
    })
    expect(result).toEqual({ ok: true })
    expect(fetchMock).toHaveBeenCalledWith(
      "https://slack.com/api/files.upload",
      expect.objectContaining({ method: "POST" }),
    )
  })

  it("includes Bearer token in Authorization header", async () => {
    const fetchMock = vi.fn(async () => Response.json({ ok: true }))
    await sendSlackOutboundFile({
      token: "xoxb-my",
      channel: "C1",
      filePath: "/x",
      fileName: "x.bin",
      bytes: Buffer.from("hi"),
      fetch: fetchMock as typeof fetch,
    })
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit
    expect((init.headers as Record<string, string>).authorization).toBe("Bearer xoxb-my")
  })

  it("trims whitespace from token", async () => {
    const fetchMock = vi.fn(async () => Response.json({ ok: true }))
    await sendSlackOutboundFile({
      token: "  xoxb-trim  ",
      channel: "C1",
      filePath: "/x",
      fileName: "x.bin",
      bytes: Buffer.from("hi"),
      fetch: fetchMock as typeof fetch,
    })
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit
    expect((init.headers as Record<string, string>).authorization).toBe("Bearer xoxb-trim")
  })

  it("appends channels, filename, and file fields to FormData", async () => {
    const fetchMock = vi.fn(async () => Response.json({ ok: true }))
    await sendSlackOutboundFile({
      token: "xoxb",
      channel: "C99",
      filePath: "/report.pdf",
      fileName: "report.pdf",
      bytes: Buffer.from("pdf-content"),
      fetch: fetchMock as typeof fetch,
    })
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit
    const form = init.body as FormData
    expect(form.get("channels")).toBe("C99")
    expect(form.get("filename")).toBe("report.pdf")
    expect(form.get("file")).toBeInstanceOf(Blob)
  })

  it("appends initial_comment when comment set", async () => {
    const fetchMock = vi.fn(async () => Response.json({ ok: true }))
    await sendSlackOutboundFile({
      token: "xoxb",
      channel: "C1",
      filePath: "/x",
      fileName: "x.bin",
      bytes: Buffer.from("hi"),
      comment: "see attached",
      fetch: fetchMock as typeof fetch,
    })
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit
    const form = init.body as FormData
    expect(form.get("initial_comment")).toBe("see attached")
  })

  it("trims whitespace from comment and skips if empty", async () => {
    const fetchMock = vi.fn(async () => Response.json({ ok: true }))
    await sendSlackOutboundFile({
      token: "xoxb",
      channel: "C1",
      filePath: "/x",
      fileName: "x.bin",
      bytes: Buffer.from("hi"),
      comment: "   ",
      fetch: fetchMock as typeof fetch,
    })
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit
    const form = init.body as FormData
    expect(form.has("initial_comment")).toBe(false)
  })

  it("appends thread_ts when threadTs set", async () => {
    const fetchMock = vi.fn(async () => Response.json({ ok: true }))
    await sendSlackOutboundFile({
      token: "xoxb",
      channel: "C1",
      filePath: "/x",
      fileName: "x.bin",
      bytes: Buffer.from("hi"),
      threadTs: "1234.567",
      fetch: fetchMock as typeof fetch,
    })
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit
    const form = init.body as FormData
    expect(form.get("thread_ts")).toBe("1234.567")
  })

  it("returns error when API returns ok=false with error code", async () => {
    const fetchMock = vi.fn(async () =>
      Response.json({ ok: false, error: "file_too_large" }),
    )
    const result = await sendSlackOutboundFile({
      token: "xoxb",
      channel: "C1",
      filePath: "/big.bin",
      fileName: "big.bin",
      bytes: Buffer.from("x"),
      fetch: fetchMock as typeof fetch,
    })
    expect(result).toEqual({ ok: false, reason: "file_too_large" })
  })

  it("returns error on HTTP failure with no error field", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ ok: false }), { status: 503 }),
    )
    const result = await sendSlackOutboundFile({
      token: "xoxb",
      channel: "C1",
      filePath: "/x",
      fileName: "x.bin",
      bytes: Buffer.from("x"),
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
    const result = await sendSlackOutboundFile({
      token: "xoxb",
      channel: "C1",
      filePath: "/x",
      fileName: "x.bin",
      bytes: Buffer.from("x"),
      fetch: fetchMock as typeof fetch,
      timeoutMs: 50,
    })
    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(result.reason).toContain("slack files.upload timeout")
    expect(result.reason).toContain("50ms")
  })

  it("returns generic error on non-abort failure", async () => {
    const fetchMock = vi.fn(async () => {
      throw new Error("network down")
    })
    const result = await sendSlackOutboundFile({
      token: "xoxb",
      channel: "C1",
      filePath: "/x",
      fileName: "x.bin",
      bytes: Buffer.from("x"),
      fetch: fetchMock as typeof fetch,
    })
    expect(result).toEqual({ ok: false, reason: "network down" })
  })
})