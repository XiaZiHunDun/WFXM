import { describe, expect, it } from "vitest"
import { parseInlineApprovalIntent } from "./inline-approval-intent.js"

describe("parseInlineApprovalIntent", () => {
  it("detects approve phrases", () => {
    expect(parseInlineApprovalIntent("确认")).toBe("approve")
    expect(parseInlineApprovalIntent("  同意  ")).toBe("approve")
    expect(parseInlineApprovalIntent("Approve")).toBe("approve")
  })

  it("detects deny phrases", () => {
    expect(parseInlineApprovalIntent("拒绝")).toBe("deny")
    expect(parseInlineApprovalIntent("取消")).toBe("deny")
  })

  it("detects single-char + emoji approve (P0 fix 2026-09-04)", () => {
    expect(parseInlineApprovalIntent("y")).toBe("approve")
    expect(parseInlineApprovalIntent("Y")).toBe("approve")
    expect(parseInlineApprovalIntent("  👌  ")).toBe("approve")
    expect(parseInlineApprovalIntent("✅")).toBe("approve")
    expect(parseInlineApprovalIntent("👍")).toBe("approve")
  })

  it("detects single-char + emoji deny (P0 fix 2026-09-04)", () => {
    expect(parseInlineApprovalIntent("n")).toBe("deny")
    expect(parseInlineApprovalIntent("N")).toBe("deny")
    expect(parseInlineApprovalIntent("❌")).toBe("deny")
    expect(parseInlineApprovalIntent("👎")).toBe("deny")
  })

  it("returns null for normal chat", () => {
    expect(parseInlineApprovalIntent("请帮我发文件")).toBeNull()
    expect(parseInlineApprovalIntent("确认发送文件")).toBeNull()
  })
})
