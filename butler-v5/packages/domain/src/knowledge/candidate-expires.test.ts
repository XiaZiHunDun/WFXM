import { describe, expect, it } from "vitest"
import {
  expireOldCandidates,
  DEFAULT_EXPIRE_TTL_MS,
} from "./candidate-expires.js"

describe("expireOldCandidates", () => {
  const baseMs = Date.parse("2026-09-01T00:00:00Z")
  const makeStore = (
    candidates: { id: string; createdAtMs: number }[],
    markExpiredResult?: Map<string, boolean>,
  ) => {
    const listExpiredCandidates = async (input: {
      olderThanMs: number
      limit?: number
    }) => {
      return candidates
        .filter((c) => c.createdAtMs < input.olderThanMs)
        .slice(0, input.limit ?? 1000)
        .map((c) => ({ id: c.id, createdAt: new Date(c.createdAtMs) }))
    }
    const markExpired = async (ids: readonly string[]) => {
      return ids.map((id) => ({
        id,
        updated: markExpiredResult?.get(id) ?? true,
      }))
    }
    return { listExpiredCandidates, markExpired }
  }

  it("returns zeros when no candidates older than threshold", async () => {
    const store = makeStore([])
    const result = await expireOldCandidates({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- test stub
      store: store as any,
      now: new Date(baseMs),
      ttlMs: DEFAULT_EXPIRE_TTL_MS,
    })
    expect(result.scanned).toBe(0)
    expect(result.expired).toBe(0)
  })

  it("7-day boundary — just over expires, just under does not", async () => {
    const sevenDays = 7 * 24 * 3_600_000
    const justOver = baseMs - sevenDays - 1000
    const justUnder = baseMs - sevenDays + 1000
    const store = makeStore([
      { id: "a", createdAtMs: justOver },
      { id: "b", createdAtMs: justUnder },
    ])
    const result = await expireOldCandidates({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- test stub
      store: store as any,
      now: new Date(baseMs),
      ttlMs: sevenDays,
    })
    expect(result.scanned).toBe(1)
    expect(result.expired).toBe(1)
  })

  it("counts only those actually updated (idempotent)", async () => {
    const store = makeStore(
      [{ id: "a", createdAtMs: baseMs - DEFAULT_EXPIRE_TTL_MS - 1000 }],
      new Map([["a", false]]),
    )
    const result = await expireOldCandidates({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- test stub
      store: store as any,
      now: new Date(baseMs),
      ttlMs: DEFAULT_EXPIRE_TTL_MS,
    })
    expect(result.scanned).toBe(1)
    expect(result.expired).toBe(0)
  })

  it("propagates markExpired errors", async () => {
    const errorStore = {
      listExpiredCandidates: async () => [{ id: "a", createdAt: new Date(0) }],
      markExpired: async () => {
        throw new Error("db down")
      },
    }
    await expect(
      expireOldCandidates({
        // eslint-disable-next-line @typescript-eslint/no-explicit-any -- test stub
        store: errorStore as any,
        now: new Date(baseMs),
        ttlMs: DEFAULT_EXPIRE_TTL_MS,
      }),
    ).rejects.toThrow("db down")
  })

  it("olderThanMs equals nowMs - ttlMs", async () => {
    const store = makeStore([])
    const now = new Date(baseMs)
    const ttl = 1000
    const result = await expireOldCandidates({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- test stub
      store: store as any,
      now,
      ttlMs: ttl,
    })
    expect(result.olderThanMs).toBe(baseMs - 1000)
  })
})