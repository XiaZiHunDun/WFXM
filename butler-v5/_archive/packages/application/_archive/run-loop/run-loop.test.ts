import { describe, it, expect } from "vitest"
import { Effect, Layer, Exit } from "effect"
import {
  runLoop,
  MockLLMLive,
  MockToolExecutorLive,
  MockGuardServiceLive,
  MockLoopInterruptLive,
  MockEventStoreLive,
} from "./index.js"
import { LLMService } from "@butler/ports"
import { makeTestConfig } from "@butler/config"
import type { ConversationId } from "@butler/domain"

const cid = "conv-test-1" as unknown as ConversationId

// 组合所有 Mock Layer
const AllTestLayers = Layer.mergeAll(
  MockLLMLive,
  MockToolExecutorLive,
  MockGuardServiceLive,
  MockLoopInterruptLive,
  MockEventStoreLive,
  makeTestConfig(),
)

// 永不完成的 Mock LLM（每次回复不含 done/完成）
const NeverCompleteLLM = Layer.succeed(
  LLMService,
  LLMService.of({
    complete: (messages) =>
      Effect.sync(() => {
        const lastMsg = messages[messages.length - 1]
        return {
          id: `reply-${Date.now()}`,
          conversationId: lastMsg?.conversationId ?? ("mock" as ConversationId),
          role: "assistant" as const,
          content: "Let me think more about this...",
          createdAt: Date.now(),
        }
      }),
    stream: () => {
      throw new Error("Mock LLM does not support streaming")
    },
  }),
)

describe("run-loop", () => {
  it("completes with IntentReceipt for simple message", async () => {
    const program = Effect.provide(
      runLoop({
        conversationId: cid,
        userMessage: "Add a login button",
      }),
      AllTestLayers,
    )

    const result = await Effect.runPromise(program)
    expect(result.intent).toBe("Add a login button")
    expect(result.authorAgent).toBe("claude-3-5-sonnet")
    expect(result.reviewerAgent).toBe("claude-3-5-haiku")
    expect(result.id).toMatch(/^receipt-/)
  })

  it("fails with ContextOverflow when exceeding max iterations", async () => {
    const lowConfig = makeTestConfig({
      loop: { maxIterations: 3, timeoutMs: 600_000 },
    })
    const lowLayers = Layer.mergeAll(
      NeverCompleteLLM,
      MockToolExecutorLive,
      MockGuardServiceLive,
      MockLoopInterruptLive,
      MockEventStoreLive,
      lowConfig,
    )

    const program = Effect.provide(
      runLoop({
        conversationId: cid,
        userMessage: "A task that will loop forever",
      }),
      lowLayers,
    )

    const exit = await Effect.runPromiseExit(program)
    expect(Exit.isFailure(exit)).toBe(true)
    if (Exit.isFailure(exit)) {
      expect(exit.cause._tag).toBe("Fail")
      if (exit.cause._tag === "Fail") {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const err = exit.cause.error as any
        expect(err._tag).toBe("ContextOverflow")
      }
    }
  })
})
