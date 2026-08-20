import { describe, expect, it } from "vitest"
import { readFileSync, readdirSync, statSync } from "node:fs"
import { join, relative } from "node:path"

function listTsFiles(dir: string): string[] {
  const out: string[] = []
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry)
    const stat = statSync(path)
    if (stat.isDirectory()) out.push(...listTsFiles(path))
    else if (entry.endsWith(".ts")) out.push(path)
  }
  return out
}

function forbiddenSideEffectImports(src: string): string[] {
  const hits: string[] = []
  if (/\brunTool\b/.test(src) && /from\s+["']@butler\/runtime\/tool-runtime/.test(src)) {
    hits.push("runTool from @butler/runtime/tool-runtime")
  }
  return hits
}

describe("side-effect throat", () => {
  it("apps production sources must not call runTool directly", () => {
    const root = join(process.cwd(), "apps")
    const violations: string[] = []
    for (const file of listTsFiles(root)) {
      if (file.endsWith(".test.ts")) continue
      const src = readFileSync(file, "utf8")
      const hits = forbiddenSideEffectImports(src)
      if (hits.length > 0) {
        violations.push(`${relative(process.cwd(), file)}: ${hits.join(", ")}`)
      }
    }
    expect(violations).toEqual([])
  })
})
