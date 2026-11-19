// Anchors: domain is pure (zero project deps, zero Node I/O). Replaces the
// former §5 guard; asserts imports only, not how purity is implemented.
import { describe, expect, it } from "vitest"
import { readFileSync, readdirSync, statSync } from "node:fs"
import { join, relative } from "node:path"

const domainRoot = join(process.cwd(), "packages/domain/src")

function listTs(dir: string): string[] {
  const out: string[] = []
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === "dist") continue
    const p = join(dir, entry)
    const st = statSync(p)
    if (st.isDirectory()) out.push(...listTs(p))
    else if (entry.endsWith(".ts") && !entry.endsWith(".test.ts")) out.push(p)
  }
  return out
}

const FORBIDDEN = [
  /from\s+["']@butler\//,
  /from\s+["']node:/,
  /from\s+["']effect["']/,
  /from\s+["']drizzle/,
  /from\s+["']postgres/,
  /from\s+["']\.\.\/\.\.\/(?:ports|infrastructure|application|adapters|runtime|persistence)/,
]

describe("domain zero I/O", () => {
  it("domain imports no project package, no Node builtin, no I/O driver", () => {
    const violations: string[] = []
    for (const file of listTs(domainRoot)) {
      const src = readFileSync(file, "utf8")
      for (const pat of FORBIDDEN) {
        if (pat.test(src)) violations.push(`${relative(process.cwd(), file)}: ${pat.source}`)
      }
    }
    expect(violations).toEqual([])
  })
})
