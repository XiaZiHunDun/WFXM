// domain/memory/pure.ts
// 记忆域纯函数 — Dream 两阶段记忆巩固评分

import type { MemoryRecord, DreamPhase, DreamResult, RecallEntry, RecallResult } from "./types.js"

// ─── 记忆重要性评分 ─────────────────────────────────────
export function scoreImportance(record: MemoryRecord, recencyWeight: number = 0.5): number {
  const ageMs = Date.now() - record.metadata.createdAt
  const ageDays = ageMs / (1000 * 60 * 60 * 24)
  const recency = Math.max(0, 1 - ageDays * recencyWeight)
  return record.metadata.importance * recency
}

// ─── Dream 阶段选择 ─────────────────────────────────────
export function pickDreamPhase(
  records: readonly MemoryRecord[],
  consolidateThreshold: number = 100,
): DreamPhase {
  if (records.length > consolidateThreshold) {
    return "consolidate-deep"
  }
  return "consolidate"
}

// ─── 记忆修剪策略 ───────────────────────────────────────
export function pruneLowImportance(
  records: readonly MemoryRecord[],
  minScore: number = 0.2,
): readonly MemoryRecord[] {
  return records.filter((r) => scoreImportance(r) >= minScore)
}

// ─── Dream 结果构建 ─────────────────────────────────────
export function buildDreamResult(
  phase: DreamPhase,
  newMemories: readonly MemoryRecord[],
  prunedIds: readonly string[],
): DreamResult {
  return {
    newMemories,
    prunedIds: prunedIds as unknown as DreamResult["prunedIds"],
    phase,
  }
}

// ─── R2.2 召回策略 [spec §5.2] ──────────────────────────
// 半衰期 30 天
const HALF_LIFE_MS = 30 * 24 * 60 * 60 * 1000

// 时间衰减：基于 lastAccessAt 的指数衰减
export function decayScore(record: RecallEntry, now: number): number {
  const age = Math.max(0, now - record.lastAccessAt)
  const factor = Math.pow(0.5, age / HALF_LIFE_MS)
  return record.weight * factor
}

// 按衰减分数排序（最新访问优先）
export function rankByRecency(
  records: readonly RecallEntry[],
  now: number,
): readonly RecallEntry[] {
  return [...records].sort((a, b) => decayScore(b, now) - decayScore(a, now))
}

// 多路召回融合：按 id 去重，取每条记录的最高分
export function fuseResults(
  a: readonly RecallResult[],
  b: readonly RecallResult[],
): readonly RecallResult[] {
  const map = new Map<string, RecallResult>()
  for (const r of [...a, ...b]) {
    const existing = map.get(r.record.id)
    if (!existing || r.score > existing.score) {
      map.set(r.record.id, r)
    }
  }
  return Array.from(map.values())
}
