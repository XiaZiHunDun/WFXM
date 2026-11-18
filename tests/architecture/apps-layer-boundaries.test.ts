import { describe, expect, it } from "vitest"
import { readFileSync, readdirSync, statSync } from "node:fs"
import { join, relative } from "node:path"

function listTsFiles(dir: string): string[] {
  const out: string[] = []
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === "dist") continue
    const path = join(dir, entry)
    const stat = statSync(path)
    if (stat.isDirectory()) out.push(...listTsFiles(path))
    else if (entry.endsWith(".ts")) out.push(path)
  }
  return out
}

function forbiddenImports(src: string): string[] {
  const hits: string[] = []
  if (src.includes("@butler/infrastructure")) hits.push("@butler/infrastructure")
  if (src.includes("@butler/application")) hits.push("@butler/application")
  if (src.includes("_archive/packages/infrastructure/src/persistence/schema")) {
    hits.push("_archive/packages/infrastructure/src/persistence/schema")
  }
  return hits
}

describe("apps layer boundaries", () => {
  it("apps production sources must not import infrastructure or application layers", () => {
    const root = join(process.cwd(), "apps")
    const violations: string[] = []
    for (const file of listTsFiles(root)) {
      if (file.endsWith(".test.ts")) continue
      const src = readFileSync(file, "utf8")
      const hits = forbiddenImports(src)
      if (hits.length > 0) {
        violations.push(`${relative(process.cwd(), file)}: ${hits.join(", ")}`)
      }
    }
    expect(violations).toEqual([])
  })
})
