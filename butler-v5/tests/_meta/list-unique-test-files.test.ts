import { describe, expect, it } from "vitest"
import { execFileSync } from "node:child_process"

describe("test discovery", () => {
  it("reports unique test source files", () => {
    const out = execFileSync("bash", ["scripts/list-test-files.sh"], {
      cwd: process.cwd(),
      encoding: "utf8",
    })
    const files = out.trim().split("\n").filter(Boolean)
    const unique = new Set(files)
    expect(files.length).toBe(unique.size)
    expect(files.length).toBeGreaterThan(0)
  })
})
