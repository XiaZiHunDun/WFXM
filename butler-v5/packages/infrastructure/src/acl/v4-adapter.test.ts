import { describe, it, expect } from "vitest"
import { Effect } from "effect"
import { MockV4AdapterLive, V4Adapter } from "./v4-adapter.js"

describe("infrastructure/acl/v4-adapter", () => {
  it("importV4Conversation returns stub", async () => {
    const program = Effect.gen(function* () {
      const v4 = yield* V4Adapter
      return yield* v4.importV4Conversation("v4-conv-1")
    })

    const result = await Effect.runPromise(Effect.provide(program, MockV4AdapterLive))
    expect(result.id).toBe("v4-conv-1")
    expect(result.state).toBe("completed")
  })

  it("exportV5Receipt succeeds", async () => {
    const program = Effect.gen(function* () {
      const v4 = yield* V4Adapter
      yield* v4.exportV5Receipt({
        id: "r-1",
        intent: "test",
        evidenceFiles: [],
        locDelta: { added: 0, removed: 0 },
        chainCompleteness: 1,
        guardFindings: [],
        authorAgent: "test",
        createdAt: 1,
      })
      return true
    })

    const result = await Effect.runPromise(Effect.provide(program, MockV4AdapterLive))
    expect(result).toBe(true)
  })

  it("subscribeMessages returns empty", async () => {
    const program = Effect.gen(function* () {
      const v4 = yield* V4Adapter
      return yield* v4.subscribeMessages()
    })

    const result = await Effect.runPromise(Effect.provide(program, MockV4AdapterLive))
    expect(result).toEqual([])
  })
})
