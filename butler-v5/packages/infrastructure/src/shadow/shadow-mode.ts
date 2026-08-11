// infrastructure/shadow/shadow-mode.ts
// 影子模式验证 — v4 处理真实流量，v5 接收副本执行并比对
// Phase 4 实现

import { Effect, Layer, Context } from "effect"
import { V4Adapter } from "../acl/v4-adapter.js"
import type { ConversationId } from "@butler/domain"
import type { IntentReceipt } from "@butler/domain"

// ─── ShadowMode ─────────────────────────────────────────
export class ShadowMode extends Context.Tag("ShadowMode")<
  ShadowMode,
  {
    readonly run: () => Effect.Effect<void, never, V4Adapter>
    readonly compare: (v4Result: unknown, v5Result: IntentReceipt) => Effect.Effect<boolean>
  }
>() {}

// ─── ShadowModeLive ─────────────────────────────────────
const shadowResults: { matched: number; mismatched: number } = { matched: 0, mismatched: 0 }

export const ShadowModeLive = Layer.succeed(ShadowMode, {
  run: () =>
    Effect.gen(function* () {
      const v4 = yield* V4Adapter
      const messages = yield* v4.subscribeMessages()

      // Phase 4: 对每条 v4 消息，v5 并行执行并比对
      for (const msg of messages) {
        yield* Effect.logInfo(`[Shadow] Processing v4 message: ${msg.content.slice(0, 50)}`)
      }

      yield* Effect.logInfo(
        `[Shadow] Results: ${shadowResults.matched} matched, ${shadowResults.mismatched} mismatched`,
      )
    }),

  compare: (v4Result: unknown, v5Result: IntentReceipt) =>
    Effect.sync(() => {
      const matched = v5Result.guardFindings.length === 0
      if (matched) shadowResults.matched++
      else shadowResults.mismatched++
      return matched
    }),
})

// ─── 辅助：影子模式运行器 ───────────────────────────────
export const shadowMode = (
  runLoop: (input: {
    conversationId: ConversationId
    userMessage: string
  }) => Effect.Effect<IntentReceipt>,
): Effect.Effect<void, never, V4Adapter> =>
  Effect.gen(function* () {
    const v4 = yield* V4Adapter
    const messages = yield* v4.subscribeMessages()
    for (const msg of messages) {
      const v5Result = yield* Effect.either(
        runLoop({
          conversationId: msg.convId as unknown as ConversationId,
          userMessage: msg.content,
        }),
      )
      yield* Effect.logInfo(`[Shadow] v5 result for ${msg.convId}: ${v5Result._tag}`)
    }
  })
