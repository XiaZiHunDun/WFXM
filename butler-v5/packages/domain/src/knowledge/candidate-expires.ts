/**
 * G1: candidate expires cleanup pure function (§12).
 * Lists candidate rows older than now-ttlMs and marks them status='expired'.
 * Caller owns logger / error handling.
 */

/** Minimal store contract — persistence's DurableMemoryStore satisfies via structural typing. */
export interface ExpireCandidatesStore {
  readonly listExpiredCandidates: (input: {
    readonly olderThanMs: number
    readonly limit?: number
  }) => Promise<readonly { id: string; createdAt: Date }[]>
  readonly markExpired: (
    ids: readonly string[],
  ) => Promise<readonly { id: string; updated: boolean }[]>
}

export interface ExpireOldCandidatesInput {
  readonly store: ExpireCandidatesStore
  readonly now: Date
  readonly ttlMs: number
  readonly batchLimit?: number
}

export interface ExpireOldCandidatesResult {
  readonly scanned: number
  readonly expired: number
  readonly olderThanMs: number
}

export const DEFAULT_EXPIRE_TTL_MS = 7 * 24 * 3_600_000 // 7 days
export const DEFAULT_EXPIRE_BATCH_LIMIT = 1000

export async function expireOldCandidates(
  input: ExpireOldCandidatesInput,
): Promise<ExpireOldCandidatesResult> {
  const batchLimit = input.batchLimit ?? DEFAULT_EXPIRE_BATCH_LIMIT
  const olderThanMs = input.now.getTime() - input.ttlMs
  const candidates = await input.store.listExpiredCandidates({
    olderThanMs,
    limit: batchLimit,
  })
  const ids = candidates.map((c) => c.id)
  if (ids.length === 0) {
    return { scanned: 0, expired: 0, olderThanMs }
  }
  const results = await input.store.markExpired(ids)
  const expired = results.filter((r) => r.updated).length
  return { scanned: ids.length, expired, olderThanMs }
}