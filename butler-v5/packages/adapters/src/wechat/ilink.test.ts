import { describe, expect, it, vi } from "vitest"
import {
  extractIlinkText,
  ilinkGetUpdates,
  ilinkSendMessage,
  inboundFromIlinkMsg,
  ITEM_TEXT,
} from "./ilink.js"

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
