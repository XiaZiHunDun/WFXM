import { describe, expect, it } from "vitest"
import { existsSync, readFileSync } from "node:fs"
import { join } from "node:path"

describe("unwired packages archival", () => {
  it("archived delegate-task lives under application/_archive", () => {
    const root = join(process.cwd(), "packages/application/_archive/delegate-task")
    expect(existsSync(join(root, "index.ts"))).toBe(true)
    expect(existsSync(join(process.cwd(), "packages/application/src/delegate-task"))).toBe(false)
  })

  it("archived infrastructure llm/wechat live under _archive", () => {
    expect(existsSync(join(process.cwd(), "packages/infrastructure/_archive/llm/index.ts"))).toBe(
      true,
    )
    expect(
      existsSync(join(process.cwd(), "packages/infrastructure/_archive/wechat/index.ts")),
    ).toBe(true)
    expect(existsSync(join(process.cwd(), "packages/infrastructure/src/llm"))).toBe(false)
    expect(existsSync(join(process.cwd(), "packages/infrastructure/src/wechat"))).toBe(false)
  })

  it("application index does not export archived modules", () => {
    const src = readFileSync(join(process.cwd(), "packages/application/src/index.ts"), "utf8")
    expect(src.includes("delegate-task/index.js")).toBe(false)
    expect(src.includes("run-workflow/index.js")).toBe(false)
    expect(src.includes("dream/index.js")).toBe(false)
  })

  it("archived run-workflow and dream live under application/_archive", () => {
    expect(existsSync(join(process.cwd(), "packages/application/_archive/run-workflow/index.ts"))).toBe(
      true,
    )
    expect(existsSync(join(process.cwd(), "packages/application/_archive/dream/index.ts"))).toBe(true)
    expect(existsSync(join(process.cwd(), "packages/application/src/run-workflow"))).toBe(false)
    expect(existsSync(join(process.cwd(), "packages/application/src/dream"))).toBe(false)
  })
})
