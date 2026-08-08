import { describe, expect, it } from "vitest"
import { decidePermission } from "./pure.js"
import type { ApprovalRequest, Capability, PermissionPolicy, ToolNameRef } from "./types.js"

describe("decidePermission", () => {
  const basePolicy: PermissionPolicy = {
    allowed: [{ tool: "read_file" as ToolNameRef, paths: ["*"] }],
    denied: [],
    requireApproval: [{ tool: "terminal" as ToolNameRef, approver: "owner" }],
  }
  const request: ApprovalRequest = {
    tool: "read_file" as ToolNameRef,
    resource: { path: "/ws/file.txt" },
  }
  it("allows whitelisted tool", () => {
    const d = decidePermission(request, basePolicy)
    expect(d._tag).toBe("Allow")
    if (d._tag === "Allow") {
      const cap: Capability = d.capability
      expect(cap.tool).toBe(request.tool)
    }
  })
  it("denies blacklisted tool", () => {
    const req: ApprovalRequest = {
      tool: "shell" as ToolNameRef,
      resource: { path: "/" },
    }
    expect(decidePermission(req, basePolicy)._tag).toBe("Deny")
  })
  it("requires approval for sensitive tool", () => {
    const req: ApprovalRequest = {
      tool: "terminal" as ToolNameRef,
      resource: { path: "/" },
    }
    expect(decidePermission(req, basePolicy)._tag).toBe("RequireApproval")
  })
  it("denies when no rule matches", () => {
    const req: ApprovalRequest = {
      tool: "mystery_tool" as ToolNameRef,
      resource: { path: "/foo" },
    }
    expect(decidePermission(req, basePolicy)._tag).toBe("Deny")
  })
  it("path prefix matching respects * suffix", () => {
    const policy: PermissionPolicy = {
      allowed: [{ tool: "read_file" as ToolNameRef, paths: ["/ws/*"] }],
      denied: [],
      requireApproval: [],
    }
    const okReq: ApprovalRequest = {
      tool: "read_file" as ToolNameRef,
      resource: { path: "/ws/file.txt" },
    }
    const noMatch: ApprovalRequest = {
      tool: "read_file" as ToolNameRef,
      resource: { path: "/other/file.txt" },
    }
    expect(decidePermission(okReq, policy)._tag).toBe("Allow")
    expect(decidePermission(noMatch, policy)._tag).toBe("Deny")
  })
})
