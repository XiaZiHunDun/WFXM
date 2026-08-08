import { describe, expect, it } from "vitest"
import { readFileSync, readdirSync, statSync } from "node:fs"
import { join } from "node:path"

const domainRoot = join(process.cwd(), "packages/domain/src")

function listTs(dir: string): string[] {
  const out: string[] = []
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry)
    const st = statSync(p)
    if (st.isDirectory()) out.push(...listTs(p))
    else if (entry.endsWith(".ts") && !entry.endsWith(".test.ts")) out.push(p)
  }
  return out
}

const FORBIDDEN = [
  /from\s+["']effect["']/,
  /from\s+["']drizzle/,
  /from\s+["']postgres/,
  /from\s+["']node:fs/,
  /from\s+["']node:http/,
  /from\s+["']\.\.\/\.\.\/ports/,
  /from\s+["']\.\.\/\.\.\/infrastructure/,
  /from\s+["']\.\.\/\.\.\/application/,
  /from\s+["']\.\.\/\.\.\/adapters/,
]

describe("domain zero I/O", () => {
  it("forbids infrastructure imports", () => {
    const files = listTs(domainRoot)
    const violations: string[] = []
    for (const file of files) {
      const src = readFileSync(file, "utf8")
      for (const pat of FORBIDDEN) {
        if (pat.test(src)) violations.push(`${file}: ${pat}`)
      }
    }
    expect(violations).toEqual([])
  })
})
