import { mkdtempSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { buildToolApprovalPreview, isApprovalPreviewEnabled } from "./approval-preview.js"

const ENABLED = { BUTLER_V5_APPROVAL_PREVIEW: "1" } as NodeJS.ProcessEnv

describe("buildToolApprovalPreview", () => {
  let root: string

  beforeEach(() => {
    root = mkdtempSync(join(tmpdir(), "wfxm-approval-preview-"))
  })

  afterEach(() => {
    rmSync(root, { recursive: true, force: true })
  })

  it("is off by default", () => {
    expect(isApprovalPreviewEnabled({})).toBe(false)
    expect(
      buildToolApprovalPreview({
        capability: "run_command",
        args: { argv: ["pnpm", "test"] },
        workspaceRoot: root,
        env: {},
      }),
    ).toBeNull()
  })

  it("renders the full command", () => {
    expect(
      buildToolApprovalPreview({
        capability: "run_command",
        args: { argv: ["pnpm", "test"] },
        workspaceRoot: root,
        env: ENABLED,
      }),
    ).toBe("命令：pnpm test")
  })

  it("treats a missing file as new content", () => {
    const preview = buildToolApprovalPreview({
      capability: "write_file",
      args: { path: "demo-note.txt", content: "a\nb" },
      workspaceRoot: root,
      env: ENABLED,
    })
    expect(preview).toContain("文件：demo-note.txt")
    expect(preview).toContain("新增 2 行，删除 0 行")
  })

  it("diffs against the existing file", () => {
    writeFileSync(join(root, "note.txt"), "line1\nline2\n")
    const preview = buildToolApprovalPreview({
      capability: "write_file",
      args: { path: "note.txt", content: "line1\nline3\n" },
      workspaceRoot: root,
      env: ENABLED,
    })
    expect(preview).toContain("- line2")
    expect(preview).toContain("+ line3")
  })

  it("returns null for paths outside the workspace and unknown capabilities", () => {
    expect(
      buildToolApprovalPreview({
        capability: "write_file",
        args: { path: "../escape.txt", content: "x" },
        workspaceRoot: root,
        env: ENABLED,
      }),
    ).toBeNull()
    expect(
      buildToolApprovalPreview({
        capability: "read_file",
        args: { path: "note.txt" },
        workspaceRoot: root,
        env: ENABLED,
      }),
    ).toBeNull()
  })
})
