// domain/permissions/types.ts
// 权限域 ADT — Permission、decidePermission、ApprovalRequest、PolicyDecision

import type { LoadBearingMark } from "../guards/types.js"

// ─── 权限动作 ───────────────────────────────────────────
export type Permission =
  | { readonly _tag: "ReadFile"; readonly path: string }
  | { readonly _tag: "WriteFile"; readonly path: string; readonly reason: string }
  | { readonly _tag: "ExecuteCommand"; readonly command: string }
  | { readonly _tag: "Delegate"; readonly toAgent: string }
  | { readonly _tag: "ModifyLoadBearing"; readonly path: string; readonly ownerApprovalSig: string }

// ─── 权限决策（纯函数） ─────────────────────────────────
export function decidePermission(
  perm: Permission,
  marks: readonly LoadBearingMark[],
): "allow" | "deny" | "require-owner-approval" {
  if (perm._tag === "WriteFile") {
    const matched = marks.find((m) => m.path === perm.path && m.ownerApproved)
    if (matched) return "require-owner-approval"
  }
  if (perm._tag === "ModifyLoadBearing" && !perm.ownerApprovalSig) {
    return "deny"
  }
  return "allow"
}

// ─── R2.3 纯 Policy Engine 类型 ─────────────────────────
// 参考 spec §8.2 — 纯 Policy Engine 用 ApprovalRequest + PermissionPolicy 输入，
// 输出 PolicyDecision ADT（不再返回 string union）。
export type ToolNameRef = string & { readonly __brand: "ToolNameRef" }
export type PathPattern = string

export interface ApprovalRequest {
  readonly tool: ToolNameRef
  readonly resource: { readonly path: string }
  readonly action?: "read" | "write" | "execute" | "delegate"
}

export interface Capability {
  readonly tool: ToolNameRef
  readonly expiresAt: number
}

export interface PermissionPolicy {
  readonly allowed: readonly {
    tool: ToolNameRef
    paths: readonly PathPattern[]
  }[]
  readonly denied: readonly { tool: ToolNameRef; reason: string }[]
  readonly requireApproval: readonly { tool: ToolNameRef; approver: string }[]
}

export type PolicyDecision =
  | { readonly _tag: "Allow"; readonly capability: Capability }
  | { readonly _tag: "Deny"; readonly reason: string }
  | { readonly _tag: "RequireApproval"; readonly approver: string }
