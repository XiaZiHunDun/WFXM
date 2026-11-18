/**
 * G2: candidate dedup via trigram Jaccard (§12).
 * Pure function — caller owns store + threshold + status filter.
 */
import type { DurableMemoryStatus } from "./durable-memory.js"

/** Minimal store contract — persistence's DurableMemoryStore satisfies via structural typing. */
export interface DedupStore {
  readonly findCandidatesForDedup: (input: {
    readonly subject: string
    readonly statuses: readonly DurableMemoryStatus[]
    readonly recentMs: number
    readonly limit: number
  }) => Promise<readonly { id: string; content: string; status: DurableMemoryStatus }[]>
}

export interface FindSimilarMemoriesInput {
  readonly store: DedupStore
  readonly subject: string
  readonly content: string
  /** 0..1; >= threshold 视为重复 */
  readonly threshold: number
  readonly statuses: readonly DurableMemoryStatus[]
  /** default 90d */
  readonly recentMs?: number
  /** default 50 */
  readonly limit?: number
}

export interface SimilarMemoryMatch {
  readonly id: string
  readonly content: string
  readonly status: DurableMemoryStatus
  readonly similarity: number
}

export interface FindSimilarMemoriesResult {
  readonly best: SimilarMemoryMatch | null
  readonly scanned: number
}

/** Trigram (3-char window) Jaccard similarity. Returns 0..1. */
export function trigramJaccard(a: string, b: string): number {
  const aGrams = trigrams(a)
  const bGrams = trigrams(b)
  if (aGrams.size === 0 && bGrams.size === 0) return 1.0
  let intersect = 0
  for (const g of aGrams) if (bGrams.has(g)) intersect++
  const union = aGrams.size + bGrams.size - intersect
  return union === 0 ? 0 : intersect / union
}

function trigrams(s: string): Set<string> {
  const padded = `  ${s.trim().toLowerCase()}  `
  const grams = new Set<string>()
  for (let i = 0; i < padded.length - 2; i++) {
    grams.add(padded.slice(i, i + 3))
  }
  return grams
}

export async function findSimilarMemories(
  input: FindSimilarMemoriesInput,
): Promise<FindSimilarMemoriesResult> {
  const recentMs = input.recentMs ?? 90 * 24 * 3_600_000
  const limit = input.limit ?? 50
  const candidates = await input.store.findCandidatesForDedup({
    subject: input.subject,
    statuses: input.statuses,
    recentMs,
    limit,
  })
  let best: SimilarMemoryMatch | null = null
  for (const c of candidates) {
    const similarity = trigramJaccard(input.content, c.content)
    if (similarity >= input.threshold && (best === null || similarity > best.similarity)) {
      best = { id: c.id, content: c.content, status: c.status, similarity }
    }
  }
  return { best, scanned: candidates.length }
}
