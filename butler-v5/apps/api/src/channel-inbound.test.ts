import { describe, expect, it } from "vitest"
import { createHmac } from "node:crypto"
import {
  parseSlackEventPayload,
  parseTelegramUpdate,
  telegramWebhookAuthorized,
  verifySlackSignature,
} from "./channel-inbound.js"

describe("slack channel adapter", () => {
  it("returns url_verification challenge", () => {
    const parsed = parseSlackEventPayload({ type: "url_verification", challenge: "abc" })
    expect(parsed).toEqual({ kind: "challenge", challenge: "abc" })
  })

  it("parses user message events", () => {
    const parsed = parseSlackEventPayload({
      type: "event_callback",
      event: { type: "message", user: "U1", text: "hello", ts: "123.456" },
    })
    expect(parsed).toEqual({
      kind: "message",
      fromSubject: "U1",
      content: "hello",
      messageId: "slack-123.456",
    })
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
    })
  })

  it("checks optional webhook secret header", () => {
    expect(
      telegramWebhookAuthorized({ BUTLER_V5_TELEGRAM_WEBHOOK_SECRET: "tok" }, "tok"),
    ).toBe(true)
    expect(
      telegramWebhookAuthorized({ BUTLER_V5_TELEGRAM_WEBHOOK_SECRET: "tok" }, "bad"),
    ).toBe(false)
  })
})
