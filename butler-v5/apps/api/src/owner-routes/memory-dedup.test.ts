/**
 * G2 dedup guard — owner-routes/memory-dedup.ts unit tests.
 *
 * Audit F-09 (D57): makeDedupChecker is shared by both /v1/owner/memories and
 * /v1/owner/documents routes. Lock the fail-open contract (§20 #11) and the
 * force-bypass path so a future refactor cannot accidentally block owner writes.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { DurableMemoryStore } from "@butler/persistence"

const findSimilarMemoriesMock = vi.fn()

vi.mock("@butler/domain/knowledge/dedup.js", () => ({
  findSimilarMemories: (...args: unknown[]) => findSimilarMemoriesMock(...args),
}))

const { makeDedupChecker } = await import("./memory-dedup.js")

function stubStore(): DurableMemoryStore {
  return {} as DurableMemoryStore
}

describe("makeDedupChecker", () => {
  let stderrSpy: ReturnType<typeof vi.spyOn>
  let savedEnv: NodeJS.ProcessEnv

  beforeEach(() => {
    savedEnv = { ...process.env }
    stderrSpy = vi.spyOn(console, "error").mockImplementation(() => undefined)
    findSimilarMemoriesMock.mockReset()
  })

  afterEach(() => {
    process.env = savedEnv
    stderrSpy.mockRestore()
    vi.resetModules()
  })

  it("returns null when dedup config is disabled (threshold=0)", async () => {
    process.env["BUTLER_V5_MEMORY_DEDUP_THRESHOLD"] = "0"
    const check = makeDedupChecker()
    const result = await check({
      store: stubStore(),
      subject: "owner",
      content: "x",
      force: undefined,
    })
    expect(result).toBeNull()
    expect(findSimilarMemoriesMock).not.toHaveBeenCalled()
  })

  it("returns null when force=true (owner-bypass path)", async () => {
    process.env["BUTLER_V5_MEMORY_DEDUP_THRESHOLD"] = "0.85"
    const check = makeDedupChecker()
    const result = await check({
      store: stubStore(),
      subject: "owner",
      content: "x",
      force: true,
    })
    expect(result).toBeNull()
    expect(findSimilarMemoriesMock).not.toHaveBeenCalled()
    expect(stderrSpy).toHaveBeenCalledWith(
      expect.stringContaining("[memory-dedup] forced duplicate"),
    )
  })

  it("returns match when findSimilarMemories returns a best candidate", async () => {
    process.env["BUTLER_V5_MEMORY_DEDUP_THRESHOLD"] = "0.85"
    findSimilarMemoriesMock.mockResolvedValueOnce({
      best: {
        id: "m1",
        similarity: 0.93,
        status: "confirmed" as const,
      },
    })
    const check = makeDedupChecker()
    const result = await check({
      store: stubStore(),
      subject: "owner",
      content: "matching content",
      force: undefined,
    })
    expect(result).toEqual({
      existingMemoryId: "m1",
      similarity: 0.93,
      status: "confirmed",
    })
  })

  it("returns null when findSimilarMemories returns best=null (no similar)", async () => {
    process.env["BUTLER_V5_MEMORY_DEDUP_THRESHOLD"] = "0.85"
    findSimilarMemoriesMock.mockResolvedValueOnce({ best: null })
    const check = makeDedupChecker()
    const result = await check({
      store: stubStore(),
      subject: "owner",
      content: "novel content",
      force: undefined,
    })
    expect(result).toBeNull()
  })

  it("fails open (returns null + logs stderr) when findSimilarMemories throws (§20 #11)", async () => {
    process.env["BUTLER_V5_MEMORY_DEDUP_THRESHOLD"] = "0.85"
    findSimilarMemoriesMock.mockRejectedValueOnce(new Error("DB connection lost"))
    const check = makeDedupChecker()
    const result = await check({
      store: stubStore(),
      subject: "owner",
      content: "x",
      force: undefined,
    })
    expect(result).toBeNull()
    expect(stderrSpy).toHaveBeenCalledWith(
      "[memory-dedup] check failed:",
      "DB connection lost",
    )
  })
})
