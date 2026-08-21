import { describe, expect, it } from "vitest"
import {
  buildApiRunTrigger,
  buildChannelRunTrigger,
  buildWechatRunTrigger,
  validateRunTrigger,
} from "./run-trigger.js"

describe("RunTrigger builders", () => {
  it("builds wechat channel trigger", () => {
    const trigger = buildWechatRunTrigger({
      userId: "wx-u1",
      conversationId: "c-wx-1",
      content: "hi",
      messageId: "msg-1",
    })
    expect(trigger.source).toBe("channel")
    expect(trigger.trustLevel).toBe("trusted")
    expect(trigger.idempotencyKey).toBe("msg-1")
  })

  it("builds slack/telegram webhook trigger", () => {
    const trigger = buildChannelRunTrigger({
      channelId: "slack",
      fromSubject: "U1",
      conversationId: "c-ch-slack-U1",
      content: "hello",
      messageId: "slack-1",
    })
    expect(trigger.source).toBe("webhook")
    expect(trigger.payload).toEqual({ channelId: "slack", content: "hello" })
  })

  it("validates required fields", () => {
    const trigger = buildApiRunTrigger({
      subject: "owner",
      idempotencyKey: "k1",
    })
    expect(validateRunTrigger(trigger)).toEqual({ ok: true })
    expect(
      validateRunTrigger({ ...trigger, idempotencyKey: "" }),
    ).toEqual({ ok: false, reason: "idempotencyKey is required" })
  })
})
