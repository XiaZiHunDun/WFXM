import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { createHmac } from "node:crypto"
import {
  handleChannelInbound,
  parseTelegramUpdate,
  telegramWebhookAuthorized,
} from "./channel-inbound.js"
import { checkInboundOrder, resetInboundOrdering } from "./inbound-ordering.js"
import type { Wiring } from "./wiring.js"
import { parseSlackEventPayload, verifySlackSignature } from "@butler/adapters/slack/index.js"

describe("slack channel adapter", () => {
  it("returns url_verification challenge", () => {
    const parsed = parseSlackEventPayload({ type: "url_verification", challenge: "abc" })
    expect(parsed).toEqual({ kind: "challenge", challenge: "abc" })
  })

  it("parses user message events", () => {
    const parsed = parseSlackEventPayload({
      type: "event_callback",
      event: {
        type: "message",
        user: "U1",
        channel: "C99",
        text: "hello",
        ts: "123.456",
      },
    })
    expect(parsed).toEqual({
      kind: "message",
      fromSubject: "U1",
      content: "hello",
      messageId: "slack-123.456",
      deliveryChannel: "C99",
      threadTs: "123.456",
      sequence: 123.456,
      occurredAtMs: 123.456 * 1000,
    })
  })

  it("parses file_share events with attachments", () => {
    const parsed = parseSlackEventPayload({
      type: "event_callback",
      event: {
        type: "message",
        subtype: "file_share",
        user: "U2",
        channel: "C1",
        text: "look",
        ts: "999.1",
        files: [{ name: "a.png", mimetype: "image/png", size: 100 }],
      },
    })
    expect(parsed.kind).toBe("message")
    if (parsed.kind !== "message") return
    expect(parsed.content).toContain("look")
    expect(parsed.content).toContain("[slack image")
    expect(parsed.media?.[0]?.name).toBe("a.png")
  })

  it("verifies slack signing secret", () => {
    const raw = '{"type":"event_callback"}'
    const ts = "1700000000"
    const sig = `v0=${createHmac("sha256", "secret").update(`v0:${ts}:${raw}`).digest("hex")}`
    expect(verifySlackSignature("secret", ts, sig, raw, 1_700_000_000_000)).toBe(true)
  })
})

describe("telegram channel adapter", () => {
  it("parses text messages", () => {
    const parsed = parseTelegramUpdate({
      update_id: 1,
      message: { message_id: 9, from: { id: 42 }, text: "hi" },
    })
    expect(parsed).toEqual({
      kind: "message",
      fromSubject: "42",
      content: "hi",
      messageId: "telegram-9",
      sequence: 9,
    })
  })

  it("parses photo-only telegram messages", () => {
    const parsed = parseTelegramUpdate({
      update_id: 2,
      message: {
        message_id: 10,
        from: { id: 7 },
        photo: [{ file_id: "small" }, { file_id: "big-photo" }],
      },
    })
    expect(parsed).toEqual({
      kind: "message",
      fromSubject: "7",
      content: "[telegram image file_id=big-photo]",
      messageId: "telegram-10",
      sequence: 10,
      media: [{ kind: "image", fileId: "big-photo", mimeType: "image/jpeg" }],
    })
  })

  it("carries the telegram message date as occurredAtMs", () => {
    const parsed = parseTelegramUpdate({
      update_id: 3,
      message: { message_id: 11, from: { id: 7 }, text: "hi", date: 1_700_000_000 },
    })
    expect(parsed).toMatchObject({ sequence: 11, occurredAtMs: 1_700_000_000_000 })
  })

  it("checks optional webhook secret header", () => {
    expect(telegramWebhookAuthorized({ BUTLER_V5_TELEGRAM_WEBHOOK_SECRET: "tok" }, "tok")).toBe(
      true,
    )
    expect(telegramWebhookAuthorized({ BUTLER_V5_TELEGRAM_WEBHOOK_SECRET: "tok" }, "bad")).toBe(
      false,
    )
  })
})

describe("inbound ordering", () => {
  beforeEach(() => {
    vi.stubEnv("BUTLER_V5_CHANNEL_ALLOWLIST", "telegram")
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it("skips an older message before appending an event", async () => {
    resetInboundOrdering()
    const appended: unknown[] = []
    const wiring = {
      eventBridge: {
        async appendConversationEvent(input: unknown) {
          appended.push(input)
        },
      },
    } as unknown as Wiring
    checkInboundOrder({ channelId: "telegram", conversationId: "conv-order", sequence: 20 })

    const result = await handleChannelInbound({
      wiring,
      channelId: "telegram",
      fromSubject: "u1",
      content: "旧消息",
      messageId: "telegram-10",
      conversationId: "conv-order",
      sequence: 10,
    })

    expect(result.skipped).toBe(true)
    expect(result.skipReason).toBe("stale_sequence")
    expect(result.meta.traces).toContain("inbound-order:stale_sequence")
    expect(appended).toHaveLength(0)
  })
})
