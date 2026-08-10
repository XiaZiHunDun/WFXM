import { describe, expect, it, vi } from "vitest"
import { Effect } from "effect"
import { makeWeChatILinkAdapter } from "./ilink.js"

describe("WeChat iLink adapter", () => {
  it("send constructs a request with the right shape", async () => {
    const fetchMock = vi.fn(
      async () => new Response(JSON.stringify({ errcode: 0, errmsg: "ok" }), { status: 200 }),
    )
    const adapter = makeWeChatILinkAdapter({
      baseUrl: "https://ilink.example.com",
      token: "tok",
      fetch: fetchMock as unknown as typeof fetch,
    })
    await Effect.runPromise(adapter.send({ to: "user-1", content: "hello" }))
    expect(fetchMock).toHaveBeenCalled()
    const call = (fetchMock as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(call?.[0]).toMatch(/\/cgi-bin\/message\/send/)
    expect(call?.[1]?.method).toBe("POST")
  })

  it("send returns an error for non-zero errcode", async () => {
    const fetchMock = vi.fn(
      async () => new Response(JSON.stringify({ errcode: 40001, errmsg: "bad" }), { status: 200 }),
    )
    const adapter = makeWeChatILinkAdapter({
      baseUrl: "https://ilink.example.com",
      token: "tok",
      fetch: fetchMock as unknown as typeof fetch,
    })
    await expect(Effect.runPromise(adapter.send({ to: "u", content: "x" }))).rejects.toThrow(
      /40001/,
    )
  })

  it("verifySignature computes the expected signature", () => {
    const adapter = makeWeChatILinkAdapter({
      baseUrl: "https://ilink.example.com",
      token: "my-token",
      fetch: (() => Promise.reject(new Error("unused"))) as unknown as typeof fetch,
    })
    expect(adapter.verifySignature("s", "t", "n", "abc")).toBe("abc")
  })
})
