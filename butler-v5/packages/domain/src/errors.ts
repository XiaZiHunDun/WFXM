// packages/domain/src/errors.ts
// Butler v5 全局错误 ADT（Phase 0 起点）

export type LoopError =
  | { readonly _tag: "LLMUnavailable"; readonly provider: string }
  | { readonly _tag: "ContextOverflow"; readonly tokens: number }
  | { readonly _tag: "ToolFailed"; readonly toolId: string; readonly cause: string }
  | { readonly _tag: "GuardRejected"; readonly reason: GuardReason }
  | { readonly _tag: "OwnerOfflineTimeout"; readonly since: number }
  | { readonly _tag: "WorkflowFailed"; readonly workflowId: string; readonly cause: LoopError }
  | { readonly _tag: "PersistenceFailed"; readonly operation: string; readonly cause: string }

// GuardReason 子类型（对应 10 条 GUARD）
export type GuardReason =
  | { readonly _tag: "MissingEvidence" }
  | { readonly _tag: "LoadBearingTouched"; readonly path: string }
  | { readonly _tag: "OwnerOffline"; readonly action: string }
  | { readonly _tag: "InvalidHumanSig"; readonly field: string }
  | { readonly _tag: "ChainIncomplete"; readonly missing: readonly string[] }
  | { readonly _tag: "VerificationLevelNotMet"; readonly required: "Fast" | "Standard" }
  | { readonly _tag: "RoleConflict"; readonly author: string; readonly reviewer: string }
  | { readonly _tag: "HealFailed"; readonly layer: "retry" | "fallback" | "owner-notify" }
  | { readonly _tag: "AntiPatternDetected"; readonly pattern: string }
  | { readonly _tag: "ChaosFailure"; readonly scenario: string }

// ─── 错误 → 修复建议（纯函数）[G-1..G-10] ─────────────
export function toFixSuggestion(err: LoopError): string {
  if (err._tag === "LLMUnavailable")
    return `Provider ${err.provider} 不可用，已触发 Retry/Fallback（[G-8]），如仍失败将通知 Owner`
  if (err._tag === "ContextOverflow") return `上下文超限（${err.tokens} tokens），请压缩或拆分任务`
  if (err._tag === "ToolFailed") return `工具 ${err.toolId} 执行失败：${err.cause}`
  if (err._tag === "GuardRejected") {
    switch (err.reason._tag) {
      case "MissingEvidence":
        return "缺少 IntentReceipt，请补充 evidenceFiles [G-1]"
      case "LoadBearingTouched":
        return `修改承重代码 ${err.reason.path} 需 Owner 签名 [G-2][G-4]`
      case "OwnerOffline":
        return `Owner 离线，${err.reason.action} 已拒绝/入队 [G-3]`
      case "InvalidHumanSig":
        return `签名验证失败：${err.reason.field} [G-4]`
      case "ChainIncomplete":
        return `多文件链路缺失：${err.reason.missing.join(", ")} [G-5]`
      case "VerificationLevelNotMet":
        return `需要 ${err.reason.required} 级验证 [G-6]`
      case "RoleConflict":
        return `作者 ${err.reason.author} 与审查者 ${err.reason.reviewer} 相同 [G-7]`
      case "HealFailed":
        return `自愈层 ${err.reason.layer} 失败，已通知 Owner [G-8]`
      case "AntiPatternDetected":
        return `检测到反模式：${err.reason.pattern} [G-9]`
      case "ChaosFailure":
        return `混沌演练失败：${err.reason.scenario} [G-10]`
      default:
        return "守卫拒绝，请查看 GuardFinding 详情"
    }
  }
  if (err._tag === "OwnerOfflineTimeout") return `Owner 离线超时（${err.since}ms），任务已暂停`
  if (err._tag === "WorkflowFailed")
    return `工作流 ${err.workflowId} 失败，原因：${toFixSuggestion(err.cause)}`
  if (err._tag === "PersistenceFailed") return `持久化操作 ${err.operation} 失败：${err.cause}`
  return "未知错误，请查看日志"
}
