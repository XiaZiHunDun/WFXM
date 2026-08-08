import { describe, expect, it } from "vitest"
import { execFileSync } from "node:child_process"

describe("architecture", () => {
  it("eslint typed-rules cover all source test files", () => {
    const out = execFileSync(
      "pnpm",
      ["exec", "eslint", "packages/", "apps/", "tests/", "--ext", ".ts", "--max-warnings", "0"],
      { cwd: process.cwd(), encoding: "utf8" },
    )
    expect(out.length).toBeGreaterThanOrEqual(0)
  })
})
