import { describe, it, expect } from "vitest"
import { Effect } from "effect"
import { dream, MockMemoryServiceLive } from "./index.js"

describe("application/dream", () => {
  it("returns DreamResult for consolidate phase", async () => {
    const program = Effect.provide(dream("consolidate"), MockMemoryServiceLive)

    const result = await Effect.runPromise(program)
    expect(result.phase).toBe("consolidate")
    expect(result.newMemories).toEqual([])
    expect(result.prunedIds).toEqual([])
  })

  it("returns DreamResult for consolidate-deep phase", async () => {
    const program = Effect.provide(dream("consolidate-deep"), MockMemoryServiceLive)

    const result = await Effect.runPromise(program)
    expect(result.phase).toBe("consolidate-deep")
    expect(result.newMemories).toEqual([])
    expect(result.prunedIds).toEqual([])
  })
})
