import { beforeEach, describe, expect, it } from "vitest"
import {
  DEFAULT_INBOUND_ORDER_WINDOW_MS,
  checkInboundOrder,
  resetInboundOrdering,
  resolveInboundOrderWindowMs,
} from "./inbound-ordering.js"

beforeEach(() => {
  resetInboundOrdering()
})

describe("checkInboundOrder", () => {
  it("rejects a strictly older sequence", () => {
    expect(checkInboundOrder({ channelId: "slack", conversationId: "c1", sequence: 20 })).toEqual({
      ok: true,
    })
    expect(checkInboundOrder({ channelId: "slack", conversationId: "c1", sequence: 10 })).toEqual({
      ok: false,
      reason: "stale_sequence",
    })
  })

  it("treats an equal sequence as a redelivery, not stale", () => {
    checkInboundOrder({ channelId: "slack", conversationId: "c1", sequence: 20 })
    expect(checkInboundOrder({ channelId: "slack", conversationId: "c1", sequence: 20 })).toEqual({
      ok: true,
    })
  })

  it("keeps different conversations independent", () => {
    checkInboundOrder({ channelId: "slack", conversationId: "c1", sequence: 20 })
    expect(checkInboundOrder({ channelId: "slack", conversationId: "c2", sequence: 10 })).toEqual({
      ok: true,
    })
  })

  it("rejects a timestamp older than the window", () => {
    checkInboundOrder({ channelId: "wechat", conversationId: "u1", occurredAtMs: 2_000_000 })
    expect(
      checkInboundOrder({ channelId: "wechat", conversationId: "u1", occurredAtMs: 1_000_000 }),
    ).toEqual({ ok: false, reason: "stale_timestamp" })
  })

  it("accepts a timestamp inside the window", () => {
    checkInboundOrder({ channelId: "wechat", conversationId: "u1", occurredAtMs: 2_000_000 })
    expect(
      checkInboundOrder({ channelId: "wechat", conversationId: "u1", occurredAtMs: 1_900_000 }),
    ).toEqual({ ok: true })
  })

  it("disables the time window when the env value is 0", () => {
    const env = { BUTLER_V5_INBOUND_ORDER_WINDOW_MS: "0" }
    checkInboundOrder({ channelId: "wechat", conversationId: "u1", occurredAtMs: 2_000_000, env })
    expect(
      checkInboundOrder({ channelId: "wechat", conversationId: "u1", occurredAtMs: 1, env }),
    ).toEqual({ ok: true })
  })

  it("passes when the channel supplies no ordering metadata", () => {
    expect(checkInboundOrder({ channelId: "wechat", conversationId: "u1" })).toEqual({ ok: true })
    expect(checkInboundOrder({ channelId: "wechat", conversationId: "u1" })).toEqual({ ok: true })
  })
})

describe("resolveInboundOrderWindowMs", () => {
  it("defaults and rejects invalid values", () => {
    expect(resolveInboundOrderWindowMs({})).toBe(DEFAULT_INBOUND_ORDER_WINDOW_MS)
    expect(resolveInboundOrderWindowMs({ BUTLER_V5_INBOUND_ORDER_WINDOW_MS: "abc" })).toBe(
      DEFAULT_INBOUND_ORDER_WINDOW_MS,
    )
  })

  it("reads zero and positive overrides", () => {
    expect(resolveInboundOrderWindowMs({ BUTLER_V5_INBOUND_ORDER_WINDOW_MS: "0" })).toBe(0)
    expect(resolveInboundOrderWindowMs({ BUTLER_V5_INBOUND_ORDER_WINDOW_MS: "5000" })).toBe(5000)
  })
})
