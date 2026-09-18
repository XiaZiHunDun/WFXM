import { describe, expect, it, vi } from "vitest"
import {
  extractIlinkText,
  extractIlinkVoiceText,
  ilinkGetUpdates,
  ilinkSendMessage,
  inboundFromIlinkMsg,
  interpretQrStatus,
  ITEM_TEXT,
} from "./ilink.js"
import { Secret } from "./secret.js"

describe("iLink protocol extract", () => {
  it("reads mock type=text + text_item.content", () => {
    expect(extractIlinkText([{ type: "text", text_item: { content: "喝茶" } }])).toBe("喝茶")
  })

  it("reads v4 type=1 + text_item.text", () => {
    expect(extractIlinkText([{ type: ITEM_TEXT, text_item: { text: "hello" } }])).toBe("hello")
  })

  it("parses inbound from mock getupdates msg", () => {
    const inbound = inboundFromIlinkMsg({
      msg_id: "mock-1",
      from_user_id: "u-wx",
      item_list: [{ type: "text", text_item: { content: "你好" } }],
      context_token: "ct-1",
    })
    expect(inbound).toEqual({
      fromUserId: "u-wx",
      content: "你好",
      messageId: "mock-1",
      contextToken: "ct-1",
    })
  })

  it("uses a media placeholder when there is no text", () => {
    const inbound = inboundFromIlinkMsg({
      msg_id: "img-1",
      from_user_id: "u-wx",
      item_list: [{ type: 2, image_item: { url: "https://cdn.example/a.jpg" } }],
    })
    expect(inbound?.content).toBe("[收到图片，当前版本暂不解析媒体]")
  })

  it("uses voice_item.text as inbound when WeChat already transcribed", () => {
    expect(extractIlinkVoiceText([{ type: 3, voice_item: { text: "帮我看看天气" } }])).toBe(
      "帮我看看天气",
    )
    const inbound = inboundFromIlinkMsg({
      msg_id: "v1",
      from_user_id: "u-wx",
      item_list: [{ type: 3, voice_item: { text: "帮我看看天气" } }],
    })
    expect(inbound?.content).toBe("帮我看看天气")
  })
})

describe("iLink HTTP client", () => {
  it("getupdates posts /ilink/bot/getupdates with sync buf", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(JSON.stringify({ ret: 0, msgs: [], get_updates_buf: "b2" }), {
          status: 200,
        }),
    )
    const result = await ilinkGetUpdates(
      { baseUrl: "http://ilink.test", token: "tok", fetch: fetchMock as unknown as typeof fetch },
      "b1",
    )
    expect(result.ok).toBe(true)
    expect(fetchMock).toHaveBeenCalled()
    const call = fetchMock.mock.calls[0]
    expect(String(call?.[0])).toBe("http://ilink.test/ilink/bot/getupdates")
    expect((call?.[1] as RequestInit).method).toBe("POST")
    const body = JSON.parse(String((call?.[1] as RequestInit).body)) as {
      get_updates_buf: string
    }
    expect(body.get_updates_buf).toBe("b1")
    const headers = (call?.[1] as RequestInit).headers as Record<string, string>
    expect(headers["Authorization"]).toBe("Bearer tok")
    expect(headers["AuthorizationType"]).toBe("ilink_bot_token")
  })

  it("sendmessage posts bot text item type=1", async () => {
    const fetchMock = vi.fn(
      async () => new Response(JSON.stringify({ ret: 0, errcode: 0 }), { status: 200 }),
    )
    const result = await ilinkSendMessage(
      { baseUrl: "http://ilink.test", token: "tok", fetch: fetchMock as unknown as typeof fetch },
      { to: "u-wx", text: "pong", contextToken: "ct-1" },
    )
    expect(result.ok).toBe(true)
    const call = fetchMock.mock.calls[0]
    expect(String(call?.[0])).toBe("http://ilink.test/ilink/bot/sendmessage")
    const body = JSON.parse(String((call?.[1] as RequestInit).body)) as {
      msg: { to_user_id: string; item_list: { type: number; text_item: { text: string } }[] }
    }
    expect(body.msg.to_user_id).toBe("u-wx")
    expect(body.msg.item_list[0]?.type).toBe(ITEM_TEXT)
    expect(body.msg.item_list[0]?.text_item.text).toBe("pong")
  })

  it("getupdates timeout returns empty ok payload", async () => {
    const fetchMock = vi.fn(async () => {
      const err = new Error("aborted")
      err.name = "AbortError"
      throw err
    })
    const result = await ilinkGetUpdates(
      {
        baseUrl: "http://ilink.test",
        token: "tok",
        fetch: fetchMock as unknown as typeof fetch,
        longPollTimeoutMs: 10,
      },
      "keep",
    )
    expect(result).toEqual({
      ok: true,
      value: { ret: 0, msgs: [], get_updates_buf: "keep" },
    })
  })
})

describe("iLink QR status", () => {
  it("reads confirmed credentials from get_qrcode_status", () => {
    // D72 T3 (audit #18 SEC-002): bot_token is now wrapped in Secret<>.
    // The test asserts the wrapper shape (constructor is private — callers
    // use Secret.create()). Cleartext access requires .unwrap() which is
    // only allowed at legitimate consumption points (env file write).
    const action = interpretQrStatus({
      status: "confirmed",
      ilink_bot_id: "bot-1",
      bot_token: "tok-1",
      baseurl: "https://ilinkai.weixin.qq.com",
      ilink_user_id: "user-1",
    })
    expect(action.kind).toBe("confirmed")
    if (action.kind !== "confirmed") throw new Error("kind narrowed")
    expect(action.accountId).toBe("bot-1")
    expect(action.token).toBeInstanceOf(Secret)
    expect(action.token.toString()).toBe("[REDACTED]")
    expect(action.token.unwrap()).toBe("tok-1")
    expect(action.baseUrl).toBe("https://ilinkai.weixin.qq.com")
    expect(action.userId).toBe("user-1")
  })
})
