import { describe, it, expect } from "vitest"
import { Effect } from "effect"
import { MockEventStoreLive } from "./eventstore-live.js"
import { EventStoreService } from "@butler/ports"
import type { ConversationEvent } from "@butler/domain"

describe("infrastructure/persistence/eventstore-live", () => {
  it("append and load events", async () => {
    const events: readonly ConversationEvent[] = [
      { _tag: "ConversationStarted", conversationId: "conv-1", createdAt: 1 },
      {
        _tag: "UserMessageAdded",
        conversationId: "conv-1",
        message: {
          id: "m1",
          content: "hello",
          role: "user",
          createdAt: 2,
          conversationId: "conv-1",
        },
      },
    ]

    const program = Effect.gen(function* () {
      const es = yield* EventStoreService
      yield* es.append("conv-1", events)
      const loaded = yield* es.load("conv-1")
      return loaded
    })

    const result = await Effect.runPromise(Effect.provide(program, MockEventStoreLive))
    expect(result).toHaveLength(2)
    expect(result[0]?._tag).toBe("ConversationStarted")
    expect(result[1]?._tag).toBe("UserMessageAdded")
  })

  it("load returns empty for unknown stream", async () => {
    const program = Effect.gen(function* () {
      const es = yield* EventStoreService
      return yield* es.load("unknown")
    })

    const result = await Effect.runPromise(Effect.provide(program, MockEventStoreLive))
    expect(result).toEqual([])
  })

  it("append accumulates events in same stream", async () => {
    const events1: readonly ConversationEvent[] = [
      { _tag: "ConversationStarted", conversationId: "conv-2", createdAt: 1 },
    ]
    const events2: readonly ConversationEvent[] = [
      {
        _tag: "UserMessageAdded",
        conversationId: "conv-2",
        message: { id: "m2", content: "hi", role: "user", createdAt: 2, conversationId: "conv-2" },
      },
    ]

    const program = Effect.gen(function* () {
      const es = yield* EventStoreService
      yield* es.append("conv-2", events1)
      yield* es.append("conv-2", events2)
      return yield* es.load("conv-2")
    })

    const result = await Effect.runPromise(Effect.provide(program, MockEventStoreLive))
    expect(result).toHaveLength(2)
  })
})
