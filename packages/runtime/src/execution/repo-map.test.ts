import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { buildRepoMap } from "./repo-map.js"

let root: string

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "repo-map-"))
})

afterEach(() => {
  rmSync(root, { recursive: true, force: true })
})

function write(path: string, content: string): void {
  const full = join(root, path)
  mkdirSync(join(full, ".."), { recursive: true })
  writeFileSync(full, content)
}

describe("buildRepoMap", () => {
  it("lists code files with a few symbols and skips vendored dirs", async () => {
    write(
      "src/butler/runtime.ts",
      "export class ButlerRuntime {}\nexport function handleTurn() {}\nexport const DEFAULT = 1\n",
    )
    write("src/index.ts", "export { ButlerRuntime } from './butler/runtime.js'\n")
    write("README.md", "# demo\n")
    write("node_modules/pkg/index.js", "export function hidden() {}\n")
    write(".git/config", "[core]\n")
    write("dist/bundle.js", "export function built() {}\n")

    const map = await buildRepoMap(root)

    expect(map).toContain("src/butler/runtime.ts")
    expect(map).toContain("ButlerRuntime")
    expect(map).toContain("handleTurn")
    expect(map).toContain("README.md")
    expect(map).not.toContain("node_modules")
    expect(map).not.toContain("dist/")
    expect(map).not.toContain("hidden")
  })

  it("stops at the character budget", async () => {
    for (let index = 0; index < 20; index += 1) {
      write(`src/file-${index}.ts`, `export function fn${index}() {}\n`)
    }

    const map = await buildRepoMap(root, { maxChars: 200 })

    expect(map.length).toBeLessThan(260)
    expect(map).toContain("仓库地图")
  })

  it("returns an empty string for a repo without code files", async () => {
    write("data.json", "{}")
    expect(await buildRepoMap(root)).toBe("")
  })

  it("respects maxDepth", async () => {
    write("src/a.ts", "export function shallow() {}\n")
    write("src/deep/deeper/b.ts", "export function deepFn() {}\n")

    const map = await buildRepoMap(root, { maxDepth: 1 })

    expect(map).toContain("src/a.ts")
    expect(map).not.toContain("deepFn")
  })
})
