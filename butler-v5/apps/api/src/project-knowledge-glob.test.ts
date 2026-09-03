import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { describe, expect, it } from "vitest"
import { listWorkspaceFilesForGlob } from "./project-knowledge-glob.js"

function makeTree(): string {
  const root = mkdtempSync(join(tmpdir(), "pk-glob-"))
  mkdirSync(join(root, "tests/fixtures/ext5"), { recursive: true })
  writeFileSync(join(root, "tests/fixtures/ext5/sample.pdf"), "pdf")
  writeFileSync(join(root, "tests/fixtures/ext5/readme.txt"), "txt")
  mkdirSync(join(root, "src/nested/deep"), { recursive: true })
  writeFileSync(join(root, "src/index.ts"), "index")
  writeFileSync(join(root, "src/nested/util.ts"), "util")
  writeFileSync(join(root, "src/nested/deep/deep.ts"), "deep")
  writeFileSync(join(root, "src/README.md"), "readme")
  // Skipped dirs must be ignored by the recursive walk.
  mkdirSync(join(root, "node_modules/pkg"), { recursive: true })
  writeFileSync(join(root, "node_modules/pkg/index.js"), "pkg")
  mkdirSync(join(root, "dist/out"), { recursive: true })
  writeFileSync(join(root, "dist/out/bundle.js"), "bundle")
  return root
}

describe("listWorkspaceFilesForGlob", () => {
  it("lists scoped single-directory globs without full-tree walk", () => {
    const root = makeTree()
    const matches = listWorkspaceFilesForGlob(root, "tests/fixtures/ext5/*.pdf")
    expect(matches).toEqual(["tests/fixtures/ext5/sample.pdf"])
    rmSync(root, { recursive: true, force: true })
  })

  it("returns [] for empty or path-traversal globs", () => {
    const root = makeTree()
    expect(listWorkspaceFilesForGlob(root, "  ")).toEqual([])
    expect(listWorkspaceFilesForGlob(root, "../outside/**")).toEqual([])
    expect(listWorkspaceFilesForGlob(root, "")).toEqual([])
    rmSync(root, { recursive: true, force: true })
  })

  it("returns the exact path for a plain existing file and [] otherwise", () => {
    const root = makeTree()
    expect(listWorkspaceFilesForGlob(root, "src/index.ts")).toEqual(["src/index.ts"])
    expect(listWorkspaceFilesForGlob(root, "src/missing.ts")).toEqual([])
    // A plain path pointing at a directory is not a file.
    expect(listWorkspaceFilesForGlob(root, "src")).toEqual([])
    rmSync(root, { recursive: true, force: true })
  })

  it("walks a /**/ prefix recursively and matches the full pattern", () => {
    const root = makeTree()
    const matches = listWorkspaceFilesForGlob(root, "src/**/*.ts")
    expect(matches).toEqual(
      expect.arrayContaining(["src/index.ts", "src/nested/util.ts", "src/nested/deep/deep.ts"]),
    )
    expect(matches).not.toContain("src/README.md")
    rmSync(root, { recursive: true, force: true })
  })

  it("walks a trailing /** prefix recursively", () => {
    const root = makeTree()
    const matches = listWorkspaceFilesForGlob(root, "src/**")
    expect(matches).toEqual(
      expect.arrayContaining(["src/index.ts", "src/nested/util.ts", "src/README.md"]),
    )
    // Skipped dirs are not descended into.
    expect(matches.some((m) => m.includes("node_modules"))).toBe(false)
    expect(matches.some((m) => m.includes("dist"))).toBe(false)
    rmSync(root, { recursive: true, force: true })
  })

  it("falls back to a full-tree walk when the pattern has no resolvable prefix", () => {
    const root = makeTree()
    const matches = listWorkspaceFilesForGlob(root, "**/*.md")
    expect(matches).toEqual(["src/README.md"])
    rmSync(root, { recursive: true, force: true })
  })

  it("caps results at maxFiles and still skips node_modules/dist", () => {
    const root = makeTree()
    const all = listWorkspaceFilesForGlob(root, "src/**", 1)
    expect(all).toHaveLength(1)
    rmSync(root, { recursive: true, force: true })
  })

  it("returns [] when the scoped directory does not exist", () => {
    const root = makeTree()
    expect(listWorkspaceFilesForGlob(root, "missing/*.ts")).toEqual([])
    rmSync(root, { recursive: true, force: true })
  })
})
