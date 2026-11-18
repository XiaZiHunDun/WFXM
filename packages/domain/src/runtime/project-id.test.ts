import { describe, expect, it } from "vitest"
import { inferProjectIdFromConversationId } from "./project-id.js"

describe("inferProjectIdFromConversationId", () => {
  it("parses wechat-style ids", () => {
    expect(inferProjectIdFromConversationId("c-wechat-user-1")).toBe("wechat")
    expect(inferProjectIdFromConversationId("c-WFXM-owner")).toBe("WFXM")
  })

  it("parses channel ids", () => {
    expect(inferProjectIdFromConversationId("c-ch-slack-U123")).toBe("channel:slack")
  })

  it("parses cli ids", () => {
    expect(inferProjectIdFromConversationId("cli-owner-abc123")).toBe("cli")
  })

  it("falls back for unknown shapes", () => {
    expect(inferProjectIdFromConversationId("random-uuid")).toBe("_default")
  })
})
