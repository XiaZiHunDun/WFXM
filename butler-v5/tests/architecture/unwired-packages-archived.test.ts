import { describe, expect, it } from "vitest"
import { existsSync } from "node:fs"
import { join } from "node:path"

describe("unwired packages archival", () => {
  it("application package moved to root _archive, not in packages tree", () => {
    expect(
      existsSync(join(process.cwd(), "_archive/packages/application/_archive/delegate-task/index.ts")),
    ).toBe(true)
    expect(
      existsSync(join(process.cwd(), "_archive/packages/application/_archive/run-loop/index.ts")),
    ).toBe(true)
    expect(existsSync(join(process.cwd(), "packages/application"))).toBe(false)
  })

  it("infrastructure package moved to root _archive, not in packages tree", () => {
    for (const dir of ["guards", "acl", "shadow", "persistence", "mcp", "llm", "wechat"]) {
      expect(
        existsSync(join(process.cwd(), `_archive/packages/infrastructure/_archive/${dir}`)),
      ).toBe(true)
    }
    // archived modules no longer resolvable under the live packages tree
    expect(existsSync(join(process.cwd(), "packages/infrastructure/src/guards"))).toBe(false)
    expect(existsSync(join(process.cwd(), "packages/infrastructure"))).toBe(false)
  })

  it("contracts package moved to root _archive, not in packages tree", () => {
    expect(existsSync(join(process.cwd(), "_archive/packages/contracts/src/index.ts"))).toBe(true)
    expect(existsSync(join(process.cwd(), "packages/contracts"))).toBe(false)
  })
})