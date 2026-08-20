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

  it("returns null for normal chat", () => {
    expect(parseInlineApprovalIntent("请帮我发文件")).toBeNull()
    expect(parseInlineApprovalIntent("确认发送文件")).toBeNull()
  })
})
