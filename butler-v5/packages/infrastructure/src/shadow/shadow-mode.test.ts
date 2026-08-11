import { describe, it, expect } from "vitest"
import { Effect } from "effect"
import { ShadowMode, ShadowModeLive, shadowMode } from "./shadow-mode.js"
import { MockV4AdapterLive } from "../acl/v4-adapter.js"
import type { ConversationId, IntentReceipt } from "@butler/domain"

describe("infrastructure/shadow/shadow-mode", () => {
  it("run completes without error", async () => {
    const runLoop = (_input: { conversationId: ConversationId; userMessage: string }) =>
      Effect.succeed({
        id: "r-1",
        intent: "test",
        evidenceFiles: [],
        locDelta: { added: 0, removed: 0 },
        chainCompleteness: 1,
        guardFindings: [],
        authorAgent: "test",
        createdAt: 1,
      } as IntentReceipt)

    const program = Effect.provide(shadowMode(runLoop), MockV4AdapterLive)

    const result = await Effect.runPromise(program)
    expect(result).toBeUndefined()
  })

  it("compare returns true for clean receipt", async () => {
    const program = Effect.gen(function* () {
      const shadow = yield* ShadowMode
      return yield* shadow.compare(
        { result: "ok" },
        {
          id: "r-1",
          intent: "test",
          evidenceFiles: [],
          locDelta: { added: 0, removed: 0 },
          chainCompleteness: 1,
          guardFindings: [],
          authorAgent: "test",
          createdAt: 1,
        },
      )
    })

    const result = await Effect.runPromise(Effect.provide(program, ShadowModeLive))
    expect(result).toBe(true)
  })

  it("compare returns false for receipt with guard findings", async () => {
    const program = Effect.gen(function* () {
      const shadow = yield* ShadowMode
      return yield* shadow.compare(
        { result: "ok" },
        {
          id: "r-2",
          intent: "test",
          evidenceFiles: [],
          locDelta: { added: 0, removed: 0 },
          chainCompleteness: 1,
          guardFindings: [
            { guard: "intent-receipt", status: "fail" as const, detail: "no evidence" },
          ],
          authorAgent: "test",
          createdAt: 1,
        },
      )
    })

    const result = await Effect.runPromise(Effect.provide(program, ShadowModeLive))
    expect(result).toBe(false)
  })
})
