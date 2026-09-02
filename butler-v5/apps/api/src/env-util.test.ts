import { describe, expect, it } from "vitest"
import { envTruthy } from "./env-util.js"

describe("envTruthy (shared env boolean convention)", () => {
  it("treats 1/true/yes/on as truthy (trimmed, case-insensitive)", () => {
    for (const truthy of ["1", "true", "yes", "on", " 1 ", "TRUE", "Yes"]) {
      expect(envTruthy(truthy)).toBe(true)
    }
  })

  it("treats empty / missing / 0 / false / off / arbitrary as falsy", () => {
    expect(envTruthy(undefined)).toBe(false)
    expect(envTruthy("")).toBe(false)
    expect(envTruthy("   ")).toBe(false)
    for (const falsy of ["0", "false", "off", "no", "2", "enabled"]) {
      expect(envTruthy(falsy)).toBe(false)
    }
  })
})
