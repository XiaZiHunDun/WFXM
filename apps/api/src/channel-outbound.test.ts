import { describe, expect, it, vi } from "vitest"
import {
  deliverSlackChannelReply,
  deliverTelegramChannelReply,
  sendTelegramOutboundMessage,
} from "./channel-outbound.js"
import { sendSlackOutboundMessage } from "@butler/adapters/slack/index.js"

function slackBodies(fetchMock: ReturnType<typeof vi.fn>): string[] {
  return fetchMock.mock.calls.map((call) => {
    const init = call[1] as RequestInit
    return (JSON.parse(String(init.body)) as { text: string }).text
  })
}

function telegramBodies(fetchMock: ReturnType<typeof vi.fn>): string[] {
  return fetchMock.mock.calls.map((call) => {
    const init = call[1] as RequestInit
    return (JSON.parse(String(init.body)) as { text: string }).text
  })
}

describe("channel outbound", () => {
  it("posts slack chat.postMessage", async () => {
    const fetchMock = vi.fn(async () => Response.json({ ok: true, ts: "123.456" }))
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
})

describe("deliverSlackChannelReply", () => {
  it("splits a long reply and strips markdown plus absolute paths", async () => {
    const fetchMock = vi.fn(async () => Response.json({ ok: true, ts: "1" }))
    const reply = [
      "```text",
      `排查步骤：${"甲".repeat(2500)}`,
      `文件在 /home/ailearn/projects/WFXM/a.ts`,
      "乙".repeat(3000),
      "```",
    ].join("\n")

    const outcome = await deliverSlackChannelReply({
      token: "xoxb-test",
      channel: "C1",
      reply,
      env: {},
      fetch: fetchMock as typeof fetch,
    })

    expect(outcome.delivered).toBe(true)
    const bodies = slackBodies(fetchMock)
    expect(bodies.length).toBeGreaterThan(1)
    for (const part of bodies) {
      expect(part.length).toBeLessThanOrEqual(3900)
      expect(part).not.toContain("```")
      expect(part).not.toContain("/home/")
    }
    expect(bodies.join("")).toContain("项目目录/a.ts")
    expect(bodies.join("")).toContain("乙".repeat(500))
  })

  it("reports which part failed instead of dropping the rest silently", async () => {
    let calls = 0
    const fetchMock = vi.fn(async () => {
      calls += 1
      return calls === 2
        ? Response.json({ ok: false, error: "rate_limited" })
        : Response.json({ ok: true, ts: String(calls) })
    })

    const outcome = await deliverSlackChannelReply({
      token: "xoxb-test",
      channel: "C1",
      reply: "甲".repeat(5000),
      env: {},
      fetch: fetchMock as typeof fetch,
    })

    expect(outcome.delivered).toBe(false)
    expect(outcome.deliveryReason).toContain("第 2/2 段")
    expect(outcome.deliveryReason).toContain("rate_limited")
  })
})

describe("deliverTelegramChannelReply", () => {
  it("splits a long reply into channel-sized parts", async () => {
    const fetchMock = vi.fn(async () => Response.json({ ok: true, result: {} }))
    const reply = `排查步骤：${"甲".repeat(5000)}`

    const outcome = await deliverTelegramChannelReply({
      token: "tg-token",
      chatId: "42",
      reply,
      env: {},
      fetch: fetchMock as typeof fetch,
    })

    expect(outcome.delivered).toBe(true)
    const bodies = telegramBodies(fetchMock)
    expect(bodies.length).toBeGreaterThan(1)
    for (const part of bodies) expect(part.length).toBeLessThanOrEqual(3900)
    expect(bodies.join("")).toHaveLength(reply.length)
  })
})
