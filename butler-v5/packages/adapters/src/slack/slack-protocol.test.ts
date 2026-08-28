import { describe, expect, it } from "vitest"
import { createHmac } from "node:crypto"
import { parseSlackEventPayload, verifySlackSignature } from "./slack-protocol.js"

describe("verifySlackSignature", () => {
  const secret = "test-secret"
  function sign(raw: string, ts: string): string {
    return `v0=${createHmac("sha256", secret).update(`v0:${ts}:${raw}`).digest("hex")}`
  }

  it("accepts correct signature within 5-min window", () => {
    const raw = '{"type":"event_callback"}'
    const ts = "1700000000"
    expect(verifySlackSignature(secret, ts, sign(raw, ts), raw, 1_700_000_000_000)).toBe(true)
  })

  it("rejects empty signing secret", () => {
    expect(verifySlackSignature("", "1700000000", "v0=abc", "body", 1_700_000_000_000)).toBe(false)
  })

  it("rejects empty timestamp header", () => {
    expect(verifySlackSignature(secret, "", "v0=abc", "body", 1_700_000_000_000)).toBe(false)
  })

  it("rejects empty signature header", () => {
    expect(verifySlackSignature(secret, "1700000000", "", "body", 1_700_000_000_000)).toBe(false)
  })

  it("rejects non-numeric timestamp", () => {
    expect(verifySlackSignature(secret, "abc", "v0=abc", "body", 1_700_000_000_000)).toBe(false)
  })

  it("rejects timestamp older than 5 minutes (replay attack)", () => {
    const raw = '{"type":"event_callback"}'
    const ts = "1700000000"
    // 6 minutes after timestamp
    expect(verifySlackSignature(secret, ts, sign(raw, ts), raw, 1_700_000_000_000 + 6 * 60_000)).toBe(false)
  })

  it("rejects timestamp more than 5 minutes in the future", () => {
    const raw = '{"type":"event_callback"}'
    const ts = "1700000000"
    // 6 minutes before timestamp
    expect(verifySlackSignature(secret, ts, sign(raw, ts), raw, 1_700_000_000_000 - 6 * 60_000)).toBe(false)
  })

  it("rejects signature with wrong secret", () => {
    const raw = '{"type":"event_callback"}'
    const ts = "1700000000"
    const wrongSig = `v0=${createHmac("sha256", "wrong-secret").update(`v0:${ts}:${raw}`).digest("hex")}`
    expect(verifySlackSignature(secret, ts, wrongSig, raw, 1_700_000_000_000)).toBe(false)
  })

  it("rejects signature with tampered body", () => {
    const raw = '{"type":"event_callback"}'
    const ts = "1700000000"
    const sig = sign(raw, ts)
    expect(verifySlackSignature(secret, ts, sig, '{"type":"DIFFERENT"}', 1_700_000_000_000)).toBe(false)
  })

  it("rejects signature with different length (constant-time guard)", () => {
    const raw = '{"type":"event_callback"}'
    const ts = "1700000000"
    const sig = sign(raw, ts)
    // Truncate signature — different length, must not crash
    expect(verifySlackSignature(secret, ts, sig.slice(0, 8), raw, 1_700_000_000_000)).toBe(false)
  })
})

describe("parseSlackEventPayload", () => {
  it("returns url_verification challenge", () => {
    expect(parseSlackEventPayload({ type: "url_verification", challenge: "abc123" })).toEqual({
      kind: "challenge",
      challenge: "abc123",
    })
  })

  it("returns invalid when url_verification missing challenge", () => {
    const parsed = parseSlackEventPayload({ type: "url_verification" })
    expect(parsed).toEqual({ kind: "invalid", reason: "missing challenge" })
  })

  it("returns invalid when challenge is non-string", () => {
    const parsed = parseSlackEventPayload({ type: "url_verification", challenge: 42 })
    expect(parsed).toEqual({ kind: "invalid", reason: "missing challenge" })
  })

  it("returns invalid for non-object body", () => {
    expect(parseSlackEventPayload(null)).toEqual({ kind: "invalid", reason: "body must be an object" })
    expect(parseSlackEventPayload("string")).toEqual({ kind: "invalid", reason: "body must be an object" })
    expect(parseSlackEventPayload(42)).toEqual({ kind: "invalid", reason: "body must be an object" })
  })

  it("returns ignore for unknown event type", () => {
    expect(parseSlackEventPayload({ type: "app_rate_limited" })).toEqual({ kind: "ignore" })
  })

  it("returns ignore when event_callback missing event field", () => {
    expect(parseSlackEventPayload({ type: "event_callback" })).toEqual({ kind: "ignore" })
  })

  it("returns ignore for non-message events", () => {
    expect(
      parseSlackEventPayload({ type: "event_callback", event: { type: "reaction_added" } }),
    ).toEqual({ kind: "ignore" })
  })

  it("returns ignore for bot_message subtype (non-user)", () => {
    expect(
      parseSlackEventPayload({
        type: "event_callback",
        event: { type: "message", subtype: "bot_message", user: "U1", channel: "C1", text: "hi" },
      }),
    ).toEqual({ kind: "ignore" })
  })

  it("returns ignore for channel_join subtype", () => {
    expect(
      parseSlackEventPayload({
        type: "event_callback",
        event: { type: "message", subtype: "channel_join", user: "U1", channel: "C1" },
      }),
    ).toEqual({ kind: "ignore" })
  })

  it("parses message event", () => {
    expect(
      parseSlackEventPayload({
        type: "event_callback",
        event: { type: "message", user: "U1", channel: "C99", text: "hello", ts: "123.456" },
      }),
    ).toEqual({
      kind: "message",
      fromSubject: "U1",
      content: "hello",
      messageId: "slack-123.456",
      deliveryChannel: "C99",
      threadTs: "123.456",
    })
  })

  it("uses thread_ts when present, not parent ts", () => {
    const parsed = parseSlackEventPayload({
      type: "event_callback",
      event: { type: "message", user: "U1", channel: "C99", text: "reply", ts: "2.000", thread_ts: "1.000" },
    })
    if (parsed.kind !== "message") throw new Error("expected message")
    expect(parsed.threadTs).toBe("1.000")
  })

  it("falls back to ts for threadTs when thread_ts absent", () => {
    const parsed = parseSlackEventPayload({
      type: "event_callback",
      event: { type: "message", user: "U1", channel: "C1", text: "hi", ts: "5.000" },
    })
    if (parsed.kind !== "message") throw new Error("expected message")
    expect(parsed.threadTs).toBe("5.000")
  })

  it("generates synthetic messageId when ts missing", () => {
    const parsed = parseSlackEventPayload({
      type: "event_callback",
      event: { type: "message", user: "U1", channel: "C1", text: "hi" },
    })
    if (parsed.kind !== "message") throw new Error("expected message")
    expect(parsed.messageId).toMatch(/^slack-\d+$/)
  })

  it("returns ignore when message missing user", () => {
    expect(
      parseSlackEventPayload({
        type: "event_callback",
        event: { type: "message", channel: "C1", text: "hi", ts: "1.0" },
      }),
    ).toEqual({ kind: "ignore" })
  })

  it("returns ignore when message missing channel", () => {
    expect(
      parseSlackEventPayload({
        type: "event_callback",
        event: { type: "message", user: "U1", text: "hi", ts: "1.0" },
      }),
    ).toEqual({ kind: "ignore" })
  })

  it("returns ignore when message has empty channel", () => {
    expect(
      parseSlackEventPayload({
        type: "event_callback",
        event: { type: "message", user: "U1", channel: "   ", text: "hi", ts: "1.0" },
      }),
    ).toEqual({ kind: "ignore" })
  })

  it("returns ignore when message has empty text and no files", () => {
    expect(
      parseSlackEventPayload({
        type: "event_callback",
        event: { type: "message", user: "U1", channel: "C1", text: "   ", ts: "1.0" },
      }),
    ).toEqual({ kind: "ignore" })
  })

  it("parses file_share with attachments and caption", () => {
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
    if (parsed.kind !== "message") throw new Error("expected message")
    expect(parsed.content).toContain("look")
    expect(parsed.content).toContain("[slack image name=a.png mimetype=image/png]")
    expect(parsed.media?.[0]?.name).toBe("a.png")
    expect(parsed.media?.[0]?.kind).toBe("image")
  })

  it("parses file_comment subtype", () => {
    const parsed = parseSlackEventPayload({
      type: "event_callback",
      event: {
        type: "message",
        subtype: "file_comment",
        user: "U1",
        channel: "C1",
        text: "comment on file",
        ts: "1.0",
        files: [{ name: "doc.pdf", mimetype: "application/pdf", size: 50 }],
      },
    })
    expect(parsed.kind).toBe("message")
  })

  it("handles file_share with empty text fallback", () => {
    const parsed = parseSlackEventPayload({
      type: "event_callback",
      event: {
        type: "message",
        subtype: "file_share",
        user: "U1",
        channel: "C1",
        ts: "1.0",
        files: [{ name: "x.jpg", mimetype: "image/jpeg", size: 10 }],
      },
    })
    if (parsed.kind !== "message") throw new Error("expected message")
    expect(parsed.content).toContain("[slack image")
    expect(parsed.content).not.toMatch(/^\s/)
  })

  it("trims leading/trailing whitespace from text", () => {
    const parsed = parseSlackEventPayload({
      type: "event_callback",
      event: { type: "message", user: "U1", channel: "C1", text: "  hello  ", ts: "1.0" },
    })
    if (parsed.kind !== "message") throw new Error("expected message")
    expect(parsed.content).toBe("hello")
  })

  it("trims whitespace from channel id", () => {
    const parsed = parseSlackEventPayload({
      type: "event_callback",
      event: { type: "message", user: "U1", channel: "  C99  ", text: "hi", ts: "1.0" },
    })
    if (parsed.kind !== "message") throw new Error("expected message")
    expect(parsed.deliveryChannel).toBe("C99")
  })

  it("omits threadTs when ts and thread_ts both empty", () => {
    const parsed = parseSlackEventPayload({
      type: "event_callback",
      event: { type: "message", user: "U1", channel: "C1", text: "hi", ts: "" },
    })
    if (parsed.kind !== "message") throw new Error("expected message")
    expect(parsed.threadTs).toBeUndefined()
  })
})