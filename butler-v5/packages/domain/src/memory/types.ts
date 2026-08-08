// domain/memory/types.ts
// 记忆域 ADT — Phase 1 最小定义（Phase 2 完整实现）

export type MemoryId = string & { readonly __brand: "MemoryId" }

export type MemoryRecord = {
  readonly id: MemoryId
  readonly content: string
  readonly embedding: readonly number[]
  readonly metadata: {
    readonly source: "conversation" | "code" | "doc" | "dream"
    readonly createdAt: number
    readonly importance: number
  }
}

export type DreamPhase = "consolidate" | "consolidate-deep"

export type DreamResult = {
  readonly newMemories: readonly MemoryRecord[]
  readonly prunedIds: readonly MemoryId[]
  readonly phase: DreamPhase
}

// ─── R2.2 召回层扁平记录 ────────────────────────────────
// 区别于 MemoryRecord：召回阶段使用扁平字段，直接承载时间衰减与权重
export type RecallEntryId = string & { readonly __brand: "RecallEntryId" }

export interface RecallEntry {
  readonly id: RecallEntryId
  readonly text: string
  readonly createdAt: number
  readonly lastAccessAt: number
  readonly weight: number
}

export interface RecallResult {
  readonly record: RecallEntry
  readonly score: number
}
