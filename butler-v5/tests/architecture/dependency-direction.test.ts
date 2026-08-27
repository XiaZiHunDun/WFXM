import { describe, expect, it } from "vitest"
import { readFileSync, readdirSync, statSync } from "node:fs"
import { join } from "node:path"

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

function findPkgImports(src: string, layer: string): string[] {
  const re = new RegExp(`from\\s+["']@butler/${layer}`, "g")
  return src.match(re) ?? []
}

describe("dependency direction", () => {
  it("domain must not depend on ports/application/infrastructure", () => {
    const files = listTs(join(process.cwd(), "packages/domain/src"))
    for (const file of files) {
      const src = readFileSync(file, "utf8")
      expect(findPkgImports(src, "ports")).toEqual([])
      expect(findPkgImports(src, "application")).toEqual([])
      expect(findPkgImports(src, "infrastructure")).toEqual([])
      expect(findPkgImports(src, "adapters")).toEqual([])
    }
  })
  it("runtime (core) must not depend on concrete adapters/persistence/config", () => {
    const files = listTs(join(process.cwd(), "packages/runtime/src"))
    for (const file of files) {
      const src = readFileSync(file, "utf8")
      expect(findPkgImports(src, "persistence")).toEqual([])
      expect(findPkgImports(src, "adapters")).toEqual([])
      expect(findPkgImports(src, "config")).toEqual([])
      expect(findPkgImports(src, "infrastructure")).toEqual([])
      expect(findPkgImports(src, "application")).toEqual([])
    }
  })
  it("ports may import only domain types", () => {
    const files = listTs(join(process.cwd(), "packages/ports/src"))
    for (const file of files) {
      const src = readFileSync(file, "utf8")
      expect(findPkgImports(src, "application")).toEqual([])
      expect(findPkgImports(src, "infrastructure")).toEqual([])
      expect(findPkgImports(src, "adapters")).toEqual([])
    }
  })
  it("archived application must not import adapters", () => {
    const files = listTs(join(process.cwd(), "_archive/packages/application/src"))
    for (const file of files) {
      const src = readFileSync(file, "utf8")
      expect(findPkgImports(src, "adapters")).toEqual([])
    }
  })
  it("archived contracts may import domain only", () => {
    const files = listTs(join(process.cwd(), "_archive/packages/contracts/src"))
    for (const file of files) {
      const src = readFileSync(file, "utf8")
      expect(findPkgImports(src, "application")).toEqual([])
      expect(findPkgImports(src, "infrastructure")).toEqual([])
      expect(findPkgImports(src, "ports")).toEqual([])
    }
  })
})
