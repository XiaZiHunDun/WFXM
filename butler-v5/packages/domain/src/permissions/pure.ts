// domain/permissions/pure.ts
// 纯 Policy Engine — decidePermission
// 参考 spec §8.2：以 ApprovalRequest + PermissionPolicy 输入，输出 PolicyDecision ADT
// 约束：不抛异常，所有错误分支以 Deny ADT 返回（tests/guard/no-layer-violation 禁止 throw）

import type {
  ApprovalRequest,
  Capability,
  PathPattern,
  PermissionPolicy,
  PolicyDecision,
  ToolNameRef,
} from "./types.js"

// ─── 路径匹配（glob 简化版：* 后缀） ─────────────────────
const matchesPath = (pattern: PathPattern, path: string): boolean => {
  if (pattern === "*") return true
  if (pattern.endsWith("*")) {
    return path.startsWith(pattern.slice(0, -1))
  }
  return pattern === path
}

const matchAllowedRule = (
  rule: { tool: ToolNameRef; paths: readonly PathPattern[] },
  tool: ToolNameRef,
  path: string,
): boolean => {
  if (rule.tool !== tool) return false
  if (rule.paths.length === 0) return true
  return rule.paths.some((p) => matchesPath(p, path))
}

// ─── 纯函数 ─────────────────────────────────────────────
export function decidePermission(
  request: ApprovalRequest,
  policy: PermissionPolicy,
): PolicyDecision {
  // 1. 黑名单优先
  for (const rule of policy.denied) {
    if (rule.tool === request.tool) {
      return { _tag: "Deny", reason: rule.reason }
    }
  }
  // 2. 需要审批
  for (const rule of policy.requireApproval) {
    if (rule.tool === request.tool) {
      return { _tag: "RequireApproval", approver: rule.approver }
    }
  }
  // 3. 白名单 + 路径匹配
  for (const rule of policy.allowed) {
    if (matchAllowedRule(rule, request.tool, request.resource.path)) {
      const capability: Capability = {
        tool: request.tool,
        expiresAt: Date.now() + 5 * 60 * 1000,
      }
      return { _tag: "Allow", capability }
    }
  }
  // 4. 默认拒绝（最小权限原则）
  return { _tag: "Deny", reason: "no matching allow rule" }
}
