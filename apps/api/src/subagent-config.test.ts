import { describe, expect, it } from "vitest"
import { isSubagentEnabled } from "./subagent-config.js"

describe("subagent-config", () => {
  it("is off by default", () => {
    expect(isSubagentEnabled({})).toBe(false)
    expect(isSubagentEnabled({ BUTLER_V5_SUBAGENT_ENABLED: "" })).toBe(false)
    expect(isSubagentEnabled({ BUTLER_V5_SUBAGENT_ENABLED: "0" })).toBe(false)
  })

  it("is on when BUTLER_V5_SUBAGENT_ENABLED=1", () => {
    expect(isSubagentEnabled({ BUTLER_V5_SUBAGENT_ENABLED: "1" })).toBe(true)
    expect(isSubagentEnabled({ BUTLER_V5_SUBAGENT_ENABLED: "true" })).toBe(true)
  })
})
