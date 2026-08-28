import { describe, expect, it, vi } from "vitest"
import { sendTelegramOutboundMessage, slackOutboundEnabled } from "./channel-outbound.js"
import { sendSlackOutboundMessage } from "@butler/adapters/slack/index.js"

describe("channel outbound", () => {
  it("posts slack chat.postMessage", async () => {
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

  it("posts telegram sendMessage", async () => {
    const fetchMock = vi.fn(async () => Response.json({ ok: true, result: {} }))
    const result = await sendTelegramOutboundMessage({
      token: "tg-token",
      chatId: "42",
      text: "hello telegram",
      fetch: fetchMock as typeof fetch,
    })
    expect(result).toEqual({ ok: true })
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/bottg-token/sendMessage")
  })

  it("detects slack outbound when bot token is set", () => {
    expect(slackOutboundEnabled({ BUTLER_V5_SLACK_BOT_TOKEN: "xoxb-1" })).toBe(true)
    expect(slackOutboundEnabled({})).toBe(false)
  })
})
