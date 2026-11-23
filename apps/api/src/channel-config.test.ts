import { describe, expect, it } from "vitest"
import {
  isChannelAllowed,
  isChannelApiEnabled,
  parseAllowedChannelIds,
  resolveChannelEngine,
  resolveChannelProjectId,
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

  it("defaults every channel to the legacy engine", () => {
    expect(resolveChannelEngine({}, "slack")).toBe("legacy")
    expect(resolveChannelEngine({ BUTLER_V5_CHANNEL_ENGINE: "legacy" }, "slack")).toBe("legacy")
    expect(resolveChannelEngine({ BUTLER_V5_CHANNEL_ENGINE: "nope" }, "slack")).toBe("legacy")
  })

  it("opts a channel into the butler engine", () => {
    expect(resolveChannelEngine({ BUTLER_V5_CHANNEL_ENGINE: "butler" }, "slack")).toBe("butler")
    expect(resolveChannelEngine({ BUTLER_V5_CHANNEL_ENGINE: " BUTLER " }, "telegram")).toBe(
      "butler",
    )
  })

  it("prefers the per-channel engine over the shared switch", () => {
    expect(
      resolveChannelEngine(
        { BUTLER_V5_CHANNEL_ENGINE: "butler", BUTLER_V5_SLACK_ENGINE: "legacy" },
        "slack",
      ),
    ).toBe("legacy")
    expect(
      resolveChannelEngine(
        { BUTLER_V5_CHANNEL_ENGINE: "legacy", BUTLER_V5_TELEGRAM_ENGINE: "butler" },
        "telegram",
      ),
    ).toBe("butler")
  })

  it("resolves the channel project with fallbacks", () => {
    expect(resolveChannelProjectId("slack", {})).toBe("wechat")
    expect(resolveChannelProjectId("slack", { BUTLER_V5_DEFAULT_PROJECT_ID: "wfxm" })).toBe("wfxm")
    expect(
      resolveChannelProjectId("slack", {
        BUTLER_V5_CHANNEL_PROJECTS: '{"slack":"LingWen1"}',
        BUTLER_V5_DEFAULT_PROJECT_ID: "wfxm",
      }),
    ).toBe("LingWen1")
    expect(
      resolveChannelProjectId("telegram", {
        BUTLER_V5_CHANNEL_PROJECTS: '{"slack":"LingWen1"}',
        BUTLER_V5_DEFAULT_PROJECT_ID: "wfxm",
      }),
    ).toBe("wfxm")
  })

  it("falls back to the default project when the map is malformed", () => {
    expect(
      resolveChannelProjectId("slack", {
        BUTLER_V5_CHANNEL_PROJECTS: "{not-json",
        BUTLER_V5_DEFAULT_PROJECT_ID: "wfxm",
      }),
    ).toBe("wfxm")
    expect(
      resolveChannelProjectId("slack", {
        BUTLER_V5_CHANNEL_PROJECTS: '["slack"]',
      }),
    ).toBe("wechat")
  })
})
