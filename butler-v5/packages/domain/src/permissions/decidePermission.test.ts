import { describe, it, expect } from "vitest"
import { decidePermission } from "./types.js"
import type { LoadBearingMark } from "../guards/types.js"
import type { Permission } from "./types.js"

const lbMarks: readonly LoadBearingMark[] = [
  {
    path: "src/loop.ts",
    reason: "核心循环",
    markedBy: "owner",
    ownerApproved: true,
  },
  {
    path: "src/config.ts",
    reason: "全局配置",
    markedBy: "ai-suggested",
    ownerApproved: false,
  },
]

describe("permissions/decidePermission", () => {
  it("allows ReadFile on any path", () => {
    const perm: Permission = { _tag: "ReadFile", path: "src/loop.ts" }
    expect(decidePermission(perm, lbMarks)).toBe("allow")
  })

  it("requires owner approval for WriteFile on load-bearing path", () => {
    const perm: Permission = { _tag: "WriteFile", path: "src/loop.ts", reason: "fix" }
    expect(decidePermission(perm, lbMarks)).toBe("require-owner-approval")
  })

  it("allows WriteFile on non-load-bearing path", () => {
    const perm: Permission = { _tag: "WriteFile", path: "src/utils.ts", reason: "add" }
    expect(decidePermission(perm, lbMarks)).toBe("allow")
  })

  it("allows WriteFile on not-yet-approved mark", () => {
    const perm: Permission = { _tag: "WriteFile", path: "src/config.ts", reason: "update" }
    expect(decidePermission(perm, lbMarks)).toBe("allow")
  })

  it("allows ExecuteCommand", () => {
    const perm: Permission = { _tag: "ExecuteCommand", command: "npm test" }
    expect(decidePermission(perm, lbMarks)).toBe("allow")
  })

  it("allows Delegate", () => {
    const perm: Permission = { _tag: "Delegate", toAgent: "coder-1" }
    expect(decidePermission(perm, lbMarks)).toBe("allow")
  })

  it("denies ModifyLoadBearing without approval sig", () => {
    const perm: Permission = {
      _tag: "ModifyLoadBearing",
      path: "src/loop.ts",
      ownerApprovalSig: "",
    }
    expect(decidePermission(perm, lbMarks)).toBe("deny")
  })

  it("allows ModifyLoadBearing with approval sig", () => {
    const perm: Permission = {
      _tag: "ModifyLoadBearing",
      path: "src/loop.ts",
      ownerApprovalSig: "valid-sig",
    }
    expect(decidePermission(perm, lbMarks)).toBe("allow")
  })
})
