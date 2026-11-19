// Anchors: dependency direction (Core → Ports → Domain only). Merged from the
// former §3 #1/#4 and §7 guards. Asserts import direction, never file contents.
import { describe, expect, it } from "vitest"
import { readFileSync, readdirSync, statSync } from "node:fs"
import { join, relative } from "node:path"

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

/** Match both package specifiers and relative workspace paths. */
function importsLayer(src: string, layer: string): boolean {
  const re = new RegExp(`from\\s+["'](?:@butler/${layer}|[^"']*packages/${layer})`, "m")
  return re.test(src)
}

function scan(dir: string, forbidden: readonly string[]): string[] {
  const violations: string[] = []
  for (const file of listTs(dir)) {
    const src = readFileSync(file, "utf8")
    for (const layer of forbidden) {
      if (importsLayer(src, layer)) violations.push(`${relative(process.cwd(), file)} → ${layer}`)
    }
  }
  return violations
}

const DOMAIN = join(process.cwd(), "packages/domain/src")
const RUNTIME = join(process.cwd(), "packages/runtime/src")
const PORTS = join(process.cwd(), "packages/ports/src")

describe("dependency direction", () => {
  it("domain depends on no project package", () => {
    expect(
      scan(DOMAIN, ["ports", "runtime", "persistence", "adapters", "config", "shared"]),
    ).toEqual([])
  })

  it("runtime (core) does not import concrete adapters/persistence/config", () => {
    expect(scan(RUNTIME, ["persistence", "adapters", "config", "shared"])).toEqual([])
  })

  it("ports depends only on domain", () => {
    expect(scan(PORTS, ["runtime", "persistence", "adapters", "config", "shared"])).toEqual([])
  })

  it("policy gate stays SDK-independent (no channel / provider SDK imports)", () => {
    const src = readFileSync(join(RUNTIME, "policy-gate.ts"), "utf8")
    const forbidden = [
      /from\s+["'](?:@butler\/adapters|[^"']*packages\/adapters)/,
      /from\s+["'](?:@butler\/persistence|[^"']*packages\/persistence)/,
      /from\s+["'][^"']*\/(?:slack|wechat|mcp)\b/,
      /from\s+["'](?:axios|node-fetch)["']/,
    ]
    const hits = forbidden.filter((re) => re.test(src)).map((re) => re.source)
    expect(hits).toEqual([])
  })
})
