import { describe, expect, it } from "vitest"
import { previewPath, renderApprovalPreview } from "./approval-preview.js"

describe("renderApprovalPreview", () => {
  it("renders the full run_command argv", () => {
    expect(
      renderApprovalPreview({ capability: "run_command", args: { argv: ["pnpm", "test"] } }),
    ).toBe("命令：pnpm test")
  })

  it("collapses newlines and truncates long commands", () => {
    expect(
      renderApprovalPreview({
        capability: "run_command",
        args: { argv: ["echo", "a\nb"] },
      }),
    ).toBe("命令：echo a b")

    const long = renderApprovalPreview({
      capability: "run_command",
      args: { argv: ["echo", "x".repeat(1_000)] },
    })
    expect(long).toContain("…（已截断）")
    expect((long ?? "").length).toBeLessThan(700)
  })

  it("renders a new file with line counts", () => {
    const preview = renderApprovalPreview({
      capability: "write_file",
      args: { path: "demo-note.txt", content: "a\nb" },
      oldContent: "",
    })
    expect(preview).toContain("文件：demo-note.txt")
    expect(preview).toContain("新增 2 行，删除 0 行")
    expect(preview).toContain("+ a")
    expect(preview).toContain("+ b")
  })

  it("renders a compact diff for overwrites", () => {
    const preview = renderApprovalPreview({
      capability: "write_file",
      args: { path: "src/a.ts", content: "line1\nline3" },
      oldContent: "line1\nline2",
    })
    expect(preview).toContain("新增 1 行，删除 1 行")
    expect(preview).toContain("- line2")
    expect(preview).toContain("+ line3")
  })

  it("truncates long diffs", () => {
    const oldContent = Array.from({ length: 40 }, (_, i) => `old-${i}`).join("\n")
    const content = Array.from({ length: 40 }, (_, i) => `new-${i}`).join("\n")
    const preview = renderApprovalPreview({
      capability: "write_file",
      args: { path: "a.txt", content },
      oldContent,
      maxLines: 4,
    })
    expect(preview).toContain("…（已截断）")
  })

  it("redacts absolute paths and returns null for unknown capabilities", () => {
    expect(previewPath("/home/me/repo/a.ts", "/home/me/repo")).toBe("a.ts")
    expect(previewPath("/tmp/secret/a.ts")).toBe("a.ts")
    expect(renderApprovalPreview({ capability: "read_file", args: { path: "a.txt" } })).toBeNull()
  })
})
