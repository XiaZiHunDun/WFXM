import { describe, it, expect } from "vitest"
import {
  scoreImportance,
  pickDreamPhase,
  pruneLowImportance,
  buildDreamResult,
  decayScore,
  fuseResults,
  rankByRecency,
} from "./pure.js"
import type { MemoryRecord, RecallEntry, RecallEntryId, RecallResult } from "./types.js"

function makeRecord(overrides: Partial<MemoryRecord> = {}): MemoryRecord {
  return {
    id: "mem-1" as MemoryRecord["id"],
    content: "test memory",
    embedding: [0.1, 0.2],
    metadata: {
      source: "conversation",
      createdAt: Date.now(),
      importance: 0.8,
    },
    ...overrides,
  } as MemoryRecord
}

describe("memory/pure", () => {
  describe("scoreImportance", () => {
    it("returns full importance for recent memory", () => {
      const record = makeRecord({
        metadata: {
          source: "conversation",
          createdAt: Date.now(),
          importance: 0.9,
        },
      })
      const score = scoreImportance(record)
      expect(score).toBeCloseTo(0.9, 1)
    })

    it("decays importance for old memory", () => {
      const record = makeRecord({
        metadata: {
          source: "conversation",
          createdAt: Date.now() - 1 * 24 * 60 * 60 * 1000, // 1 day ago
          importance: 0.9,
        },
      })
      const score = scoreImportance(record)
      expect(score).toBeLessThan(0.9)
      expect(score).toBeGreaterThan(0)
    })

    it("bottoms out at 0 for very old memory", () => {
      const record = makeRecord({
        metadata: {
          source: "conversation",
          createdAt: Date.now() - 365 * 24 * 60 * 60 * 1000, // 1 year ago
          importance: 0.9,
        },
      })
      const score = scoreImportance(record)
      expect(score).toBe(0)
    })

    it("accepts custom recency weight", () => {
      const record = makeRecord({
        metadata: {
          source: "conversation",
          createdAt: Date.now() - 5 * 24 * 60 * 60 * 1000,
          importance: 0.8,
        },
      })
      const lowWeight = scoreImportance(record, 0.1)
      const highWeight = scoreImportance(record, 0.9)
      // Higher weight = faster decay = lower score
      expect(highWeight).toBeLessThan(lowWeight)
    })
  })

  describe("pickDreamPhase", () => {
    it("returns consolidate when records <= threshold", () => {
      const records = Array.from({ length: 50 }, (_, i) =>
        makeRecord({ id: `mem-${i}` as MemoryRecord["id"] }),
      )
      expect(pickDreamPhase(records)).toBe("consolidate")
    })

    it("returns consolidate-deep when records > threshold", () => {
      const records = Array.from({ length: 150 }, (_, i) =>
        makeRecord({ id: `mem-${i}` as MemoryRecord["id"] }),
      )
      expect(pickDreamPhase(records)).toBe("consolidate-deep")
    })

    it("accepts custom threshold", () => {
      const records = Array.from({ length: 30 }, (_, i) =>
        makeRecord({ id: `mem-${i}` as MemoryRecord["id"] }),
      )
      expect(pickDreamPhase(records, 20)).toBe("consolidate-deep")
    })
  })

  describe("pruneLowImportance", () => {
    it("keeps records with score >= minScore", () => {
      const records = [
        makeRecord({
          metadata: {
            source: "conversation",
            createdAt: Date.now(),
            importance: 0.9,
          },
        }),
        makeRecord({
          metadata: {
            source: "conversation",
            createdAt: Date.now() - 100 * 24 * 60 * 60 * 1000,
            importance: 0.1,
          },
        }),
      ]
      const pruned = pruneLowImportance(records, 0.2)
      expect(pruned.length).toBe(1)
    })

    it("returns empty when all records pruned", () => {
      const records = [
        makeRecord({
          metadata: {
            source: "conversation",
            createdAt: Date.now() - 200 * 24 * 60 * 60 * 1000,
            importance: 0.1,
          },
        }),
      ]
      const pruned = pruneLowImportance(records, 0.5)
      expect(pruned).toEqual([])
    })
  })

  describe("buildDreamResult", () => {
    it("constructs a DreamResult with given inputs", () => {
      const newMemories = [makeRecord({ id: "new-1" as MemoryRecord["id"] })]
      const result = buildDreamResult("consolidate", newMemories, ["pruned-1"])
      expect(result.phase).toBe("consolidate")
      expect(result.newMemories).toBe(newMemories)
      expect(result.prunedIds).toEqual(["pruned-1"])
    })
  })

  // ─── R2.2 召回策略 ─────────────────────────────────────
  describe("memory recall (R2.2)", () => {
    const now = 1_000_000
    // 用大时间差让衰减在 30 天半衰期下有意义
    const records: RecallEntry[] = [
      {
        id: "a" as RecallEntryId,
        text: "alpha",
        createdAt: now - 100,
        lastAccessAt: now - 2_500_000_000, // ~28.9 天前，显著衰减
        weight: 0.9,
      },
      {
        id: "b" as RecallEntryId,
        text: "beta",
        createdAt: now - 1000,
        lastAccessAt: now - 1, // 1ms 前，几乎无衰减
        weight: 0.5,
      },
    ]

    it("ranks by recency (newer lastAccessAt first)", () => {
      const ranked = rankByRecency(records, now)
      expect(ranked[0]?.id).toBe("b")
      expect(ranked[1]?.id).toBe("a")
    })

    it("fuses two result sets with dedup (max-score wins)", () => {
      const firstA = records[0]
      const firstB = records[1]
      if (!firstA || !firstB) throw new Error("test fixture missing")
      const r1: RecallResult[] = [{ record: firstA, score: 0.9 }]
      const r2: RecallResult[] = [
        { record: firstA, score: 0.7 },
        { record: firstB, score: 0.5 },
      ]
      const merged = fuseResults(r1, r2)
      expect(merged.length).toBe(2)
      expect(merged.find((r) => r.record.id === "a")?.score).toBeCloseTo(0.9)
      expect(merged.find((r) => r.record.id === "b")?.score).toBeCloseTo(0.5)
    })

    it("decays an old access", () => {
      const firstA = records[0]
      if (!firstA) throw new Error("test fixture missing")
      const r = decayScore(firstA, now)
      expect(r).toBeGreaterThan(0)
      expect(r).toBeLessThan(firstA.weight)
    })

    it("keeps a freshly accessed entry near full weight", () => {
      const firstB = records[1]
      if (!firstB) throw new Error("test fixture missing")
      const r = decayScore(firstB, now)
      expect(r).toBeCloseTo(firstB.weight, 2)
    })
  })
})
