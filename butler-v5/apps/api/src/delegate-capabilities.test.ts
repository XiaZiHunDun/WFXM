import { describe, expect, it } from "vitest"
import { defaultCapabilitiesForRole } from "./delegate-capabilities.js"

describe("delegate-capabilities", () => {
  it("developer role defaults to exec capabilities", () => {
    expect(defaultCapabilitiesForRole("developer")).toEqual([
      "read_file",
      "write_file",
      "run_command",
    ])
    expect(defaultCapabilitiesForRole("dev")).toEqual(["read_file", "write_file", "run_command"])
  })

  it("other roles default to general", () => {
    expect(defaultCapabilitiesForRole("researcher")).toEqual(["general"])
    expect(defaultCapabilitiesForRole("")).toEqual(["general"])
  })
})
