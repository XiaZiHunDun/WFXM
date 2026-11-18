import { describe, expect, it } from "vitest"
import { isDevDirectExecEnabled } from "./wechat-tool-profile.js"

describe("isDevDirectExecEnabled (env boolean convention)", () => {
  it("honours the shared 1/true/yes/on convention", () => {
    for (const truthy of ["1", "true", "yes", "on"]) {
      expect(isDevDirectExecEnabled({ BUTLER_V5_DEV_DIRECT_EXEC: truthy })).toBe(true)
    }
  })

  it("treats empty / explicit falsy / missing as disabled", () => {
    expect(isDevDirectExecEnabled({})).toBe(false)
    for (const falsy of ["0", "false", "off", ""]) {
      expect(isDevDirectExecEnabled({ BUTLER_V5_DEV_DIRECT_EXEC: falsy })).toBe(false)
    }
  })
})
