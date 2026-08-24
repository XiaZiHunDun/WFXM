import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { describe, expect, it } from "vitest"
import { listWorkspaceFilesForGlob } from "./project-knowledge-glob.js"

describe("listWorkspaceFilesForGlob", () => {
  it("lists scoped single-directory globs without full-tree walk", () => {
    const root = mkdtempSync(join(tmpdir(), "pk-glob-"))
    mkdirSync(join(root, "tests/fixtures/ext5"), { recursive: true })
    writeFileSync(join(root, "tests/fixtures/ext5/sample.pdf"), "pdf")
    writeFileSync(join(root, "tests/fixtures/ext5/readme.txt"), "txt")

    const matches = listWorkspaceFilesForGlob(root, "tests/fixtures/ext5/*.pdf")
    expect(matches).toEqual(["tests/fixtures/ext5/sample.pdf"])

    rmSync(root, { recursive: true, force: true })
  })
})
