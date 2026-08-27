// infrastructure/llm — LLM 客户端 + 多 provider + 重试 [G-8]
// Phase 3 实现

import { Effect, Layer, Duration, Stream } from "effect"
import { LLMService } from "@butler/ports"
import type { ConversationId, LoopError, Message } from "@butler/domain"

// ─── 辅助：模拟 API 调用延迟 ────────────────────────────
function simulateLLMCall(messages: readonly Message[]): Effect.Effect<Message, LoopError> {
  return Effect.gen(function* () {
    const lastMsg = messages[messages.length - 1]
    const content = typeof lastMsg?.content === "string" ? lastMsg.content : ""

    // 模拟网络延迟
    yield* Effect.sleep(Duration.millis(50))

    // Phase 3: 骨架返回（Phase 4 接入真实 Anthropic/OpenAI API）
    return {
      id: `llm-${Date.now()}` as Message["id"],
      conversationId: (lastMsg?.conversationId ?? "unknown") as ConversationId,
      role: "assistant" as const,
      content: `[LLM] Response to: ${content.slice(0, 80)}...\nTask complete.`,
      createdAt: Date.now(),
    }
  })
}

// ─── LLMServiceLive（多 provider + 重试） ─────────────────
export const LLMServiceLive = Layer.effect(
  LLMService,
  Effect.sync(() => {
    // Phase 3: 从环境变量读取 provider 配置
    const globalProcess = (globalThis as { process?: { env?: Record<string, string | undefined> } })
      .process
    const env = globalProcess?.env ?? {}
    const primaryProvider = env["LLM_PRIMARY"] ?? "anthropic"

    return LLMService.of({
      complete: (messages) =>
        Effect.gen(function* () {
          // [G-8] 内建重试：主 provider 失败 → fallback
          const result = yield* Effect.either(
            simulateLLMCall(messages).pipe(
              Effect.tapError((e) =>
                Effect.logWarning(
                  `[LLM] ${primaryProvider} failed: ${(e as LoopError)._tag}, trying fallback`,
                ),
              ),
            ),
          )

          if (result._tag === "Right") return result.right

          // Fallback: 重试一次
          yield* Effect.sleep(Duration.millis(100))
          return yield* simulateLLMCall(messages)
        }),

      stream: (messages) => {
        // Phase 3: 骨架流式（Phase 4 接入 SSE）
        return Stream.fromEffect(simulateLLMCall(messages))
      },
    })
  }),
)

// ─── 测试用 Mock LLM ────────────────────────────────────
export const MockLLMLive = Layer.succeed(
  LLMService,
  LLMService.of({
    complete: (messages) =>
      Effect.sync(() => {
        const lastMsg = messages[messages.length - 1]
        return {
          id: `mock-${Date.now()}` as Message["id"],
          conversationId: (lastMsg?.conversationId ?? "mock") as ConversationId,
          role: "assistant" as const,
          content: `[Mock] Task complete.`,
          createdAt: Date.now(),
        }
      }),
    stream: () => Stream.fromEffect(Effect.succeed({} as Message)),
  }),
)
