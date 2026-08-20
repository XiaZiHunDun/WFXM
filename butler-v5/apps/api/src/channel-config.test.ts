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

  it("allowlist empty means all channels allowed", () => {
    expect(parseAllowedChannelIds({})).toEqual([])
    expect(isChannelAllowed("slack", [])).toBe(true)
  })

  it("allowlist restricts channel ids", () => {
    const list = parseAllowedChannelIds({ BUTLER_V5_CHANNEL_ALLOWLIST: "slack,api" })
    expect(isChannelAllowed("slack", list)).toBe(true)
    expect(isChannelAllowed("telegram", list)).toBe(false)
  })
})
