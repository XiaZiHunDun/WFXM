/**
 * D74 T4 (audit #20 SEC-001): unit tests for the channel-seen-ids dedup
 * cache. Locks the first-sight / duplicate / TTL semantics.
 */
import { describe, expect, it, beforeEach } from "vitest"
import {
  _resetChannelSeenForTest,
  markChannelSeen,
} from "./channel-seen-ids.js"

describe("markChannelSeen", () => {
  beforeEach(() => {
    _resetChannelSeenForTest()
  })

  it("returns true on first sight", () => {
    expect(markChannelSeen("telegram", "msg-1")).toBe(true)
  })

  it("returns false on duplicate within TTL", () => {
    expect(markChannelSeen("telegram", "msg-1")).toBe(true)
    expect(markChannelSeen("telegram", "msg-1")).toBe(false)
  })

  it("treats different channels independently", () => {
    expect(markChannelSeen("telegram", "msg-1")).toBe(true)
    expect(markChannelSeen("signal", "msg-1")).toBe(true)
    expect(markChannelSeen("telegram", "msg-1")).toBe(false)
    expect(markChannelSeen("signal", "msg-1")).toBe(false)
  })

  it("treats different messageIds independently", () => {
    expect(markChannelSeen("telegram", "msg-1")).toBe(true)
    expect(markChannelSeen("telegram", "msg-2")).toBe(true)
  })
})