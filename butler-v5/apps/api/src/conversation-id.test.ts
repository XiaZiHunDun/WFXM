/**
 * R8.x.11 — client-supplied conversationId parser.
 *
 * Spec: docs/superpowers/specs/2026-08-19-conversation-id-client-supplied-design.md
 */
import { describe, expect, it } from "vitest"
import {
  CONVERSATION_ID_MAX_LEN,
  defaultWechatConversationId,
  parseClientConversationId,
} from "./conversation-id.js"

describe("parseClientConversationId", () => {
  it("returns absent when the field is undefined", () => {
    expect(parseClientConversationId(undefined)).toEqual({ kind: "absent" })
  })

  it("returns absent when the field is null (JSON null)", () => {
    expect(parseClientConversationId(null)).toEqual({ kind: "absent" })
  })

  it("accepts a valid id", () => {
    expect(parseClientConversationId("c-wechat-u1-123")).toEqual({
      kind: "valid",
      value: "c-wechat-u1-123",
    })
  })

  it("accepts dots underscores colons and hyphens", () => {
    expect(parseClientConversationId("c.r8x11:pre_sub-1")).toEqual({
      kind: "valid",
      value: "c.r8x11:pre_sub-1",
    })
  })

  it("rejects empty string", () => {
    const r = parseClientConversationId("")
    expect(r.kind).toBe("invalid")
  })

  it("rejects whitespace-only", () => {
    const r = parseClientConversationId("   ")
    expect(r.kind).toBe("invalid")
  })

  it("rejects illegal characters", () => {
    const r = parseClientConversationId("c-wechat/../evil")
    expect(r.kind).toBe("invalid")
  })

  it("rejects ids longer than max", () => {
    const r = parseClientConversationId("x".repeat(CONVERSATION_ID_MAX_LEN + 1))
    expect(r.kind).toBe("invalid")
  })

  it("rejects non-string types", () => {
    expect(parseClientConversationId(42).kind).toBe("invalid")
    expect(parseClientConversationId({ id: "x" }).kind).toBe("invalid")
  })
})

describe("defaultWechatConversationId", () => {
  it("is stable for the same project and user", () => {
    expect(defaultWechatConversationId("wechat", "u-omit")).toBe("c-wechat-u-omit")
    expect(defaultWechatConversationId("wechat", "u-omit")).toBe(
      defaultWechatConversationId("wechat", "u-omit"),
    )
  })

  it("sanitizes illegal characters so the id still parses as valid", () => {
    const id = defaultWechatConversationId("wechat", "wxid/foo bar")
    expect(parseClientConversationId(id).kind).toBe("valid")
    expect(id).toBe("c-wechat-wxid-foo-bar")
  })
})
