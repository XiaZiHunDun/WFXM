import { describe, expect, it, vi } from "vitest"
import { transcribeDashscopeFile } from "./ilink-asr.js"

describe("transcribeDashscopeFile", () => {
  it("reads transcript from DashScope JSON", async () => {
    const fetchMock = vi.fn(
      async () => new Response(JSON.stringify({ output: { text: "你好管家" } }), { status: 200 }),
    )
    const result = await transcribeDashscopeFile({
      bytes: Buffer.from("RIFF"),
      format: "wav",
      apiKey: "sk-test",
      fetch: fetchMock as unknown as typeof fetch,
    })
    expect(result).toEqual({ ok: true, value: "你好管家" })
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("dashscope.aliyuncs.com")
  })

  it("refuses silk without a decoder", async () => {
    const result = await transcribeDashscopeFile({
      bytes: Buffer.from("silk"),
      format: "silk",
      apiKey: "sk-test",
      fetch: vi.fn() as unknown as typeof fetch,
    })
    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(result.reason).toMatch(/silk/)
  })

  it("returns false when the API errors", async () => {
    const result = await transcribeDashscopeFile({
      bytes: Buffer.from("RIFF"),
      format: "wav",
      apiKey: "sk-test",
      fetch: vi.fn(async () => new Response("fail", { status: 500 })) as unknown as typeof fetch,
    })
    expect(result.ok).toBe(false)
  })
})
