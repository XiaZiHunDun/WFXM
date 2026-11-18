import { describe, expect, it } from "vitest"
import { isMcpReadonlyAutoAllowEnabled } from "./mcp-readonly-policy.js"

describe("mcp-readonly-policy", () => {
  it("is off by default", () => {
    expect(isMcpReadonlyAutoAllowEnabled({})).toBe(false)
  })

  it("is on when BUTLER_V5_MCP_READONLY_AUTO_ALLOW=1", () => {
    expect(isMcpReadonlyAutoAllowEnabled({ BUTLER_V5_MCP_READONLY_AUTO_ALLOW: "1" })).toBe(true)
  })
})
