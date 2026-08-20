export type InlineApprovalIntent = "approve" | "deny"

const APPROVE_PHRASES = new Set([
  "确认",
  "同意",
  "批准",
  "approve",
  "yes",
  "ok",
  "好",
  "好的",
])

const DENY_PHRASES = new Set(["拒绝", "取消", "否", "deny", "no"])

/**
 * Detect short inline approval/denial replies from WeChat users.
 * Only exact matches (after trim) are accepted to avoid accidental triggers.
 */
export function parseInlineApprovalIntent(content: string): InlineApprovalIntent | null {
  const normalized = content.trim().toLowerCase()
  if (APPROVE_PHRASES.has(normalized)) return "approve"
  if (DENY_PHRASES.has(normalized)) return "deny"
  return null
}
