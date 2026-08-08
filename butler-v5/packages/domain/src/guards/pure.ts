// domain/guards/pure.ts
// 防错域纯函数 — 证据校验、链路验证、自愈选择、删除风险评估

import type { LoopError } from "../errors.js"
import type {
  DeletionRisk,
  GuardFinding,
  GuardName,
  HealLayer,
  LinkedFilesSpec,
  LoadBearingMark,
  VerificationLevel,
} from "./types.js"

// ─── 验证级别选择 ──────────────────────────────────────
export function pickVerificationLevel(
  locDelta: { added: number; removed: number },
  isGeneratedTool: boolean,
): VerificationLevel {
  if (isGeneratedTool && locDelta.added < 50) return "Fast"
  return "Standard"
}

// ─── 多文件链路校验 ────────────────────────────────────
export function verifyChain(
  spec: LinkedFilesSpec,
  evidenceFiles: readonly string[],
): { completeness: number; missing: readonly string[] } {
  const hit = evidenceFiles.filter((f) => spec.expectedLinks.includes(f))
  const missing = spec.expectedLinks.filter((f) => !evidenceFiles.includes(f))
  return {
    completeness: spec.expectedLinks.length === 0 ? 1 : hit.length / spec.expectedLinks.length,
    missing,
  }
}

// ─── 3 层自愈选择 ──────────────────────────────────────
export function pickHealLayer(error: LoopError, retryCount: number): HealLayer {
  if (retryCount < 2 && error._tag !== "GuardRejected") return "retry"
  if (error._tag === "LLMUnavailable" || error._tag === "ToolFailed") return "fallback"
  return "owner-notify"
}

// ─── 删除风险评分 ──────────────────────────────────────
export function scoreDeletionRisk(
  path: string,
  marks: readonly LoadBearingMark[],
  locRemoved: number,
): DeletionRisk {
  const matched = marks.filter((m) => m.path === path)
  const reasons: string[] = matched.map((m) => m.reason)
  let score = matched.length > 0 ? 80 : 0
  if (locRemoved > 100) {
    score += 20
    reasons.push(`删除行数 ${locRemoved} > 100`)
  }
  return { score: Math.min(score, 100), reasons }
}

// ─── 证据完整性校验 ────────────────────────────────────
export function verifyEvidence(
  evidenceFiles: readonly string[],
  locDelta: { added: number; removed: number },
): readonly GuardFinding[] {
  const findings: GuardFinding[] = []
  const guard: GuardName = "intent-receipt"

  if (evidenceFiles.length === 0) {
    findings.push({ guard, status: "fail", detail: "No evidence files provided" })
  } else {
    findings.push({
      guard,
      status: "pass",
      detail: `Evidence: ${evidenceFiles.length} files, +${locDelta.added}/-${locDelta.removed} LOC`,
    })
  }
  return findings
}

// ─── 角色分离校验 ──────────────────────────────────────
export function checkRoleSeparation(
  author: string,
  reviewer: string,
): { ok: boolean; reason?: string } {
  if (author === reviewer) {
    return { ok: false, reason: `Author "${author}" cannot review their own work` }
  }
  return { ok: true }
}
