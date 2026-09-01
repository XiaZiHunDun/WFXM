import { describe, expect, it } from "vitest"
import { findSimilarMemories, trigramJaccard } from "./dedup.js"

describe("trigramJaccard", () => {
  it("identical strings → 1.0", () => {
    expect(trigramJaccard("hello world", "hello world")).toBe(1.0)
  })

  it("empty / whitespace only → 1.0 (both empty trigram sets)", () => {
    expect(trigramJaccard("", "")).toBe(1.0)
    expect(trigramJaccard("   ", "   ")).toBe(1.0)
  })

  it("completely different → ~0", () => {
    expect(trigramJaccard("apple", "zebra")).toBe(0)
  })

  it("reorder preserves similarity (trigram captures word order)", () => {
    // "hello world" vs "world hello" — many trigrams still match
    expect(trigramJaccard("hello world", "world hello")).toBeGreaterThan(0.5)
  })
})

describe("findSimilarMemories", () => {
  const makeStore = (
    candidates: { id: string; content: string; status: "candidate" | "confirmed" | "rejected" }[],
  ) => {
    return {
      findCandidatesForDedup: async () => candidates,
    }
  }

  it("returns null best when no candidates match threshold", async () => {
    const store = makeStore([
      { id: "a", content: "completely different content here", status: "confirmed" },
    ])
    const result = await findSimilarMemories({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- test stub
      store: store as any,
      subject: "owner",
      content: "my new memory",
      threshold: 0.85,
      statuses: ["candidate", "confirmed", "rejected"],
    })
    expect(result.best).toBeNull()
    expect(result.scanned).toBe(1)
  })

  it("returns best match above threshold", async () => {
    const store = makeStore([
      { id: "a", content: "owner prefers tea", status: "confirmed" },
      { id: "b", content: "owner prefers coffee in morning", status: "candidate" },
    ])
    const result = await findSimilarMemories({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- test stub
      store: store as any,
      subject: "owner",
      content: "owner prefers tea",
      threshold: 0.85,
      statuses: ["candidate", "confirmed", "rejected"],
    })
    expect(result.best).not.toBeNull()
    expect(result.best?.id).toBe("a")
    expect(result.best?.similarity).toBe(1.0)
    expect(result.best?.status).toBe("confirmed")
  })

  it("threshold edge — exactly at threshold is included (>= semantics)", async () => {
    const store = makeStore([
      { id: "a", content: "owner prefers tea in the morning with milk", status: "confirmed" },
    ])
    const result = await findSimilarMemories({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- test stub
      store: store as any,
      subject: "owner",
      content: "owner prefers tea in the morning",
      threshold: 0.5,
      statuses: ["confirmed"],
    })
    expect(result.best).not.toBeNull()
    expect(result.scanned).toBe(1)
  })

  it("respects limit via store delegation", async () => {
    const candidates = Array.from({ length: 5 }, (_, i) => ({
      id: `c${i}`,
      content: `seed ${i} unique content ${i * 1000}`,
      status: "confirmed" as const,
    }))
    const store = {
      findCandidatesForDedup: async (input: { limit: number }) =>
        candidates.slice(0, input.limit),
    }
    const result = await findSimilarMemories({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- test stub
      store: store as any,
      subject: "owner",
      content: "totally unrelated new memory",
      threshold: 0.85,
      statuses: ["confirmed"],
      limit: 3,
    })
    expect(result.scanned).toBe(3)
    expect(result.best).toBeNull()
  })
})
