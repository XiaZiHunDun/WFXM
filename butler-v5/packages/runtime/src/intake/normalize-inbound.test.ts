import { describe, expect, it } from "vitest"
import { normalizeChannelInbound, normalizeWechatInbound } from "./normalize-inbound.js"

describe("normalizeWechatInbound", () => {
  it("builds stable conversationId, idempotencyKey, and RunTrigger", () => {
    const result = normalizeWechatInbound({
      fromUserId: "u1",
      content: "hello",
      messageId: "msg-1",
      nowMs: 1_700_000_000_000,
    })
    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.value.conversationId).toBe("c-wechat-u1")
    expect(result.value.turnId).toBe("turn-1700000000000")
    expect(result.value.projectId).toBe("wechat")
    expect(result.value.idempotencyKey).toBe("msg-1")
    expect(result.value.runTrigger.source).toBe("channel")
    expect(result.value.runTrigger.subject).toBe("u1")
    expect(result.value.runTrigger.idempotencyKey).toBe("msg-1")
    expect(result.value.runTrigger.conversationRef).toBe("c-wechat-u1")
  })

  it("rejects invalid client conversationId", () => {
    const result = normalizeWechatInbound({
      fromUserId: "u1",
      content: "x",
      conversationId: "bad/id",
    })
    expect(result).toEqual({
      ok: false,
      error: {
        kind: "invalid_conversation_id",
        reason: "conversationId contains illegal characters",
      },
    })
  })

  it("uses client conversationId when valid", () => {
    const result = normalizeWechatInbound({
      fromUserId: "u1",
      content: "x",
      conversationId: "c.custom:1",
      nowMs: 42,
    })
    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.value.conversationId).toBe("c.custom:1")
    expect(result.value.idempotencyKey).toBe("wechat-c.custom:1-turn-42")
  })
})

describe("normalizeChannelInbound", () => {
  it("builds channel projectId and webhook RunTrigger", () => {
    const result = normalizeChannelInbound({
      channelId: "slack",
      fromSubject: "U1",
      content: "hi",
      messageId: "slack-1",
      nowMs: 99,
    })
    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.value.conversationId).toBe("c-ch-slack-U1")
    expect(result.value.projectId).toBe("channel:slack")
    expect(result.value.runTrigger.source).toBe("webhook")
    expect(result.value.idempotencyKey).toBe("slack-1")
  })

  it("rejects empty channelId/subject", () => {
    const result = normalizeChannelInbound({
      channelId: "  ",
      fromSubject: "U1",
      content: "hi",
    })
    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(result.error.kind).toBe("invalid_body")
  })
})
