/**
 * 锚定防作弊层的可观察契约：工作区快照能识别新增/修改/删除，
 * 并跳过依赖目录；行级 diff 不把“替换一行”误算成增删两行。
 */
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, describe, expect, it } from "vitest"
import { diffWorkspaceSnapshots, snapshotWorkspace } from "../../scripts/eval/eval-utils.js"

describe("workspace snapshot", () => {
  let root = ""

  afterEach(() => {
    if (root) rmSync(root, { recursive: true, force: true })
  })

  function makeRoot(): string {
    root = mkdtempSync(join(tmpdir(), "eval-snapshot-"))
    return root
  }

  it("distinguishes added / modified / deleted files", () => {
    const dir = makeRoot()
    mkdirSync(join(dir, "src"), { recursive: true })
    writeFileSync(join(dir, "src/a.ts"), "a\n")
    writeFileSync(join(dir, "old.ts"), "old\n")
    const before = snapshotWorkspace(dir)

    writeFileSync(join(dir, "src/a.ts"), "a\nb\n")
    writeFileSync(join(dir, "new.ts"), "n\n")
    rmSync(join(dir, "old.ts"))
    const after = snapshotWorkspace(dir)

    const { changes } = diffWorkspaceSnapshots(before, after)
    expect(changes).toEqual([
      { path: "new.ts", change: "added", added: 1, removed: 0 },
      { path: "old.ts", change: "deleted", added: 0, removed: 1 },
      { path: "src/a.ts", change: "modified", added: 1, removed: 0 },
    ])
  })

  it("reports a one-line replacement as one added + one removed", () => {
    const dir = makeRoot()
    writeFileSync(join(dir, "a.ts"), "one\ntwo\nthree\n")
    const before = snapshotWorkspace(dir)
    writeFileSync(join(dir, "a.ts"), "one\nTWO\nthree\n")
    const after = snapshotWorkspace(dir)

    const { changes } = diffWorkspaceSnapshots(before, after)
    expect(changes).toEqual([{ path: "a.ts", change: "modified", added: 1, removed: 1 }])
  })

  it("ignores dependency and VCS directories", () => {
    const dir = makeRoot()
    mkdirSync(join(dir, "node_modules/pkg"), { recursive: true })
    mkdirSync(join(dir, ".git"), { recursive: true })
    writeFileSync(join(dir, "node_modules/pkg/index.js"), "x")
    writeFileSync(join(dir, ".git/HEAD"), "ref")
    expect(snapshotWorkspace(dir).size).toBe(0)
  })

  it("keeps the baseline hash stable when nothing changed", () => {
    const dir = makeRoot()
    writeFileSync(join(dir, "a.ts"), "same\n")
    const before = snapshotWorkspace(dir)
    const { changes, baselineHash, workspaceHash } = diffWorkspaceSnapshots(
      before,
      snapshotWorkspace(dir),
    )
    expect(changes).toEqual([])
    expect(baselineHash).toBe(workspaceHash)
    expect(baselineHash.startsWith("sha256:")).toBe(true)
  })
})
