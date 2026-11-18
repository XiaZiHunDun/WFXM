import { describe, expect, it, beforeEach } from "vitest"
import { clearSubscribeTokens, issueSubscribeToken, lookupSubscribeToken } from "./ws-subscribe.js"

describe("ws subscribe tokens", () => {
  beforeEach(() => {
    clearSubscribeTokens()
  })

  it("issues a token that resolves to the conversationId", () => {
    const issued = issueSubscribeToken("c-owner-1", { nowMs: 1_000, ttlMs: 5_000 })
    expect(issued.token.length).toBeGreaterThan(16)
    expect(issued.expiresAtMs).toBe(6_000)
    expect(lookupSubscribeToken(issued.token, { nowMs: 1_000 })?.conversationId).toBe("c-owner-1")
  })

  it("returns undefined after expiry", () => {
    const issued = issueSubscribeToken("c-owner-1", { nowMs: 1_000, ttlMs: 10 })
    expect(lookupSubscribeToken(issued.token, { nowMs: 1_011 })).toBeUndefined()
  })
})
