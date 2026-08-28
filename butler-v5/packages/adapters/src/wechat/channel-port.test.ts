import { describe, expect, it } from "vitest"
import { createWechatChannelPort } from "./channel-port.js"

const baseConfig = {
  baseUrl: "https://api.weixin.qq.com",
  token: "tkn",
  fetch: async (input: RequestInfo | URL): Promise<Response> => {
    const url = typeof input === "string" ? input : input.toString()
    if (url.endsWith("/sendmessage")) {
      return new Response(JSON.stringify({ errcode: 0, errmsg: "ok" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      })
    }
    return new Response("not found", { status: 404 })
  },
}

describe("createWechatChannelPort", () => {
  it("exposes channelKind wechat", () => {
    const port = createWechatChannelPort(baseConfig)
    expect(port.channelKind).toBe("wechat")
  })

  it("forwards address + content to ilink sendmessage", async () => {
    let capturedUrl = ""
    let capturedBody = ""
    const port = createWechatChannelPort({
      ...baseConfig,
      fetch: async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
        capturedUrl = typeof input === "string" ? input : input.toString()
        if (init && typeof init.body === "string") {
          capturedBody = init.body
        }
        return new Response(JSON.stringify({ errcode: 0 }), {
          status: 200,
          headers: { "content-type": "application/json" },
        })
      },
    })
    const result = await port.sendText({
      recipient: { address: "user-1", channelKind: "wechat" },
      content: "hello world",
    })
    expect(result.ok).toBe(true)
    expect(capturedUrl).toContain("sendmessage")
    expect(capturedBody).toContain("user-1")
    expect(capturedBody).toContain("hello world")
  })

  it("rejects empty content without calling fetch", async () => {
    let called = false
    const port = createWechatChannelPort({
      ...baseConfig,
      fetch: async () => {
        called = true
        return new Response(JSON.stringify({ errcode: 0 }), { status: 200 })
      },
    })
    const result = await port.sendText({
      recipient: { address: "user-1", channelKind: "wechat" },
      content: "",
    })
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.reason).toMatch(/empty/i)
    expect(called).toBe(false)
  })
})
