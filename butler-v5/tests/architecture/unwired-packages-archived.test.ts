import { describe, expect, it } from "vitest"
import { existsSync, readFileSync } from "node:fs"
import { join } from "node:path"

describe("unwired packages archival", () => {
  it("archived delegate-task lives under application/_archive", () => {
    const root = join(process.cwd(), "packages/application/_archive/delegate-task")
    expect(existsSync(join(root, "index.ts"))).toBe(true)
    expect(existsSync(join(process.cwd(), "packages/application/src/delegate-task"))).toBe(false)
  })

  it("archived run-loop lives under application/_archive", () => {
    expect(existsSync(join(process.cwd(), "packages/application/_archive/run-loop/index.ts"))).toBe(
      true,
    )
    expect(existsSync(join(process.cwd(), "packages/application/src/run-loop"))).toBe(false)
  })

  it("application src exports no archived modules", () => {
    const src = readFileSync(join(process.cwd(), "packages/application/src/index.ts"), "utf8")
    expect(src.includes("run-loop")).toBe(false)
    expect(src.includes("delegate-task")).toBe(false)
  })

  it("archived infrastructure modules live under _archive", () => {
    for (const dir of ["guards", "acl", "shadow", "persistence", "mcp", "llm", "wechat"]) {
      expect(
        existsSync(join(process.cwd(), `packages/infrastructure/_archive/${dir}`)),
      ).toBe(true)
      expect(existsSync(join(process.cwd(), `packages/infrastructure/src/${dir}`))).toBe(false)
    }
  })
})
