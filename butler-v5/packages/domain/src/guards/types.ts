// domain/guards/types.ts
// 防错域 ADT — IntentReceipt、GuardFinding、LoadBearingMark、VerificationLevel

// ─── IntentReceipt [G-1] ───────────────────────────────
export type IntentReceipt = {
  readonly id: string
  readonly intent: string
  readonly evidenceFiles: readonly string[]
  readonly locDelta: { readonly added: number; readonly removed: number }
  readonly chainCompleteness: number
  readonly guardFindings: readonly GuardFinding[]
  readonly authorAgent: string
  readonly reviewerAgent?: string
  readonly ownerApprovalSig?: string
  readonly createdAt: number
}

// ─── GuardFinding ───────────────────────────────────────
export type GuardFinding = {
  readonly guard: GuardName
  readonly status: "pass" | "warn" | "fail"
  readonly detail: string
}

export type GuardName =
  | "intent-receipt" // G-1: 证据门控
  | "load-bearing" // G-2: 承重代码防护
  | "owner-offline-policy" // G-3: Owner 离线策略
  | "human-sig" // G-4: 签名验证
  | "multi-file-chain" // G-5: 多文件链路
  | "role-separation" // G-6: 角色分离
  | "self-heal" // G-7: 3 层自愈

// ─── 2 级验证 [G-6] ────────────────────────────────────
export type VerificationLevel = "Fast" | "Standard"

// ─── 承重代码标记 [G-2] ────────────────────────────────
export type LoadBearingMark = {
  readonly path: string
  readonly reason: string
  readonly markedBy: "owner" | "ai-suggested" | "auto-detected"
  readonly ownerApproved: boolean
  readonly alternatives?: readonly string[]
}

// ─── 多文件链路 [G-5] ──────────────────────────────────
export type LinkedFilesSpec = {
  readonly mainFile: string
  readonly expectedLinks: readonly string[]
}

// ─── 3 层自愈 [G-8] ────────────────────────────────────
export type HealLayer = "retry" | "fallback" | "owner-notify"

// ─── 删除风险评分 [G-2] ────────────────────────────────
export type DeletionRisk = {
  readonly score: number
  readonly reasons: readonly string[]
}

// ─── 契约快照 ───────────────────────────────────────────
export type ContractSnapshot = {
  readonly loadedFiles: readonly string[]
  readonly rules: readonly ContractRule[]
  readonly loadedAt: number
}

export type ContractRule = {
  readonly pattern: string
  readonly severity: "WARN" | "BLOCK"
  readonly source: string
}
