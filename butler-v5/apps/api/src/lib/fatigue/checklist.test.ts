import { describe, test, expect } from "vitest"
import { matchSensitivity, HIGH_SENSITIVITY_TOOLS, DEFAULT_CHECKLIST_ITEMS } from "./checklist"

describe("matchSensitivity", () => {
  test("F11: send_* matches", () => {
    const result = matchSensitivity("send_email")
    expect(result?.level).toBe("high")
    expect(result?.items).toHaveLength(2)
  })

  test("F12: delete_* matches", () => {
    const result = matchSensitivity("delete_file")
    expect(result?.level).toBe("high")
  })

  test("F13: read_file does not match", () => {
    expect(matchSensitivity("read_file")).toBeNull()
  })

  test("F14: broadcast_*/external_write match", () => {
    expect(matchSensitivity("broadcast_telegram")?.level).toBe("high")
    expect(matchSensitivity("external_write_patch")?.level).toBe("high")
  })
})

describe("HIGH_SENSITIVITY_TOOLS", () => {
  test("includes 4 patterns", () => {
    expect(HIGH_SENSITIVITY_TOOLS).toEqual([
      "send_*",
      "delete_*",
      "external_write",
      "broadcast_*",
    ])
  })
})

describe("DEFAULT_CHECKLIST_ITEMS", () => {
  test("has 2 acknowledgment items", () => {
    expect(DEFAULT_CHECKLIST_ITEMS).toHaveLength(2)
    expect(DEFAULT_CHECKLIST_ITEMS[0]).toContain("后果")
  })
})