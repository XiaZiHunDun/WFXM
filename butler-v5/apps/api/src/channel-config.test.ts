import { describe, expect, it } from "vitest"
import {
  isChannelAllowed,
  isChannelApiEnabled,
  parseAllowedChannelIds,
} from "./channel-config.js"

describe("channel-config", () => {
  it("channel api is off by default", () => {
    expect(isChannelApiEnabled({})).toBe(false)
    expect(isChannelApiEnabled({ BUTLER_V5_CHANNEL_API_ENABLED: "1" })).toBe(true)
  })

  it("allowlist empty now means FAIL-CLOSED (D63 T4 F-02)", () => {
    // D63 T4 (audit #9 F-02): empty allowlist previously meant "any
    // channelId accepted" — FAIL-OPEN. Inverted to FAIL-CLOSED so an
    // operator must explicitly populate BUTLER_V5_CHANNEL_ALLOWLIST
    // to allow channels.
    expect(parseAllowedChannelIds({})).toEqual([])
    expect(isChannelAllowed("slack", [])).toBe(false)
  })

  it("allowlist restricts channel ids", () => {
    const list = parseAllowedChannelIds({ BUTLER_V5_CHANNEL_ALLOWLIST: "slack,api" })
    expect(isChannelAllowed("slack", list)).toBe(true)
    expect(isChannelAllowed("telegram", list)).toBe(false)
  })
})
