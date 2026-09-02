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

  it("rejects empty fromUserId", () => {
    const result = normalizeWechatInbound({ fromUserId: "   ", content: "x" })
    expect(result).toEqual({
      ok: false,
      error: { kind: "invalid_body", reason: "fromUserId is required" },
    })
  })

  it("rejects non-string content", () => {
    const result = normalizeWechatInbound({
      fromUserId: "u1",
      content: 42 as unknown as string,
    })
    expect(result).toEqual({
      ok: false,
      error: { kind: "invalid_body", reason: "content is required" },
    })
  })

  it("trims projectId and falls back to wechat for whitespace", () => {
    const trimmed = normalizeWechatInbound({
      fromUserId: "u1",
      content: "x",
      projectId: "  proj A  ",
      nowMs: 1,
    })
    const blank = normalizeWechatInbound({ fromUserId: "u1", content: "x", projectId: "   ", nowMs: 1 })
    expect(trimmed.ok).toBe(true)
    if (trimmed.ok) expect(trimmed.value.projectId).toBe("proj A")
    expect(blank.ok).toBe(true)
    if (blank.ok) expect(blank.value.projectId).toBe("wechat")
  })

  it("treats whitespace-only messageId as absent (generated idempotencyKey)", () => {
    const result = normalizeWechatInbound({
      fromUserId: "u1",
      content: "x",
      messageId: "  ",
      nowMs: 7,
    })
    expect(result.ok).toBe(true)
    if (result.ok) {
      expect(result.value.messageId).toBeUndefined()
      expect(result.value.idempotencyKey).toBe("wechat-c-wechat-u1-turn-7")
    }
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

  it("rejects non-string content", () => {
    const result = normalizeChannelInbound({
      channelId: "slack",
      fromSubject: "s1",
      content: 42 as unknown as string,
    })
    expect(result).toEqual({
      ok: false,
      error: { kind: "invalid_body", reason: "content is required" },
    })
  })

  it("uses messageId as idempotencyKey and propagates it to the RunTrigger", () => {
    const result = normalizeChannelInbound({
      channelId: "slack",
      fromSubject: "s1",
      content: "x",
      messageId: "m9",
      nowMs: 9,
    })
    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.value.projectId).toBe("channel:slack")
    expect(result.value.idempotencyKey).toBe("m9")
    expect(result.value.runTrigger.idempotencyKey).toBe("m9")
  })
})
