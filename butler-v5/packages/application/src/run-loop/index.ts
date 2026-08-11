// application/run-loop/run-loop.ts
// 核心 Loop 用例 — Effect 编排（Phase 1: Mock LLM 实现）

import { Effect, Layer, Stream } from "effect"
import {
  type ConversationId,
  type IntentReceipt,
  type LoopError,
  type Message,
  type ToolCall,
  makeContextWindow,
  isNearLimit,
} from "@butler/domain"
import {
  LLMService,
  ToolExecutor,
  LoopInterrupt,
  GuardService,
  EventStoreService,
  Config,
} from "@butler/ports"

// ─── 辅助函数 ───────────────────────────────────────────
function makeUserMessage(id: string, conversationId: ConversationId, content: string): Message {
  return {
    id: `${id}-user`,
    conversationId,
    role: "user",
    content,
    createdAt: Date.now(),
  }
}

function collectEvidenceFiles(messages: readonly Message[]): readonly string[] {
  const files: string[] = []
  for (const msg of messages) {
    if (msg.role === "tool" && msg.content) {
      // 从工具结果中提取文件路径
      try {
        const parsed = JSON.parse(msg.content)
        if (parsed.path) files.push(parsed.path)
      } catch {
        // 非 JSON 内容，跳过
      }
    }
  }
  return files
}

function computeLocDelta(messages: readonly Message[]): { added: number; removed: number } {
  let added = 0
  let removed = 0
  for (const msg of messages) {
    if (msg.role === "tool" && msg.content) {
      try {
        const parsed = JSON.parse(msg.content)
        if (parsed.locDelta) {
          added += parsed.locDelta.added ?? 0
          removed += parsed.locDelta.removed ?? 0
        }
      } catch {
        // 非 JSON 内容，跳过
      }
    }
  }
  return { added, removed }
}

function isComplete(reply: Message): boolean {
  // 判断：reply 内容包含完成标记
  const content = reply.content.toLowerCase()
  return content.includes("done") || content.includes("完成") || content.includes("task complete")
}

// ─── runLoop 用例 ───────────────────────────────────────
export const runLoop = (input: {
  readonly conversationId: ConversationId
  readonly userMessage: string
}): Effect.Effect<
  IntentReceipt,
  LoopError | GuardRejectedError,
  LLMService | ToolExecutor | LoopInterrupt | GuardService | EventStoreService | Config
> =>
  Effect.gen(function* (_) {
    const llm = yield* _(LLMService)
    const toolExec = yield* _(ToolExecutor)
    const guard = yield* _(GuardService)
    const interrupt = yield* _(LoopInterrupt)
    const config = yield* _(Config)

    let messages: readonly Message[] = [
      makeUserMessage("1", input.conversationId, input.userMessage),
    ]
    let iteration = 0

    while (iteration < config.loop.maxIterations) {
      iteration++

      // 检查上下文窗口
      const ctxWindow = makeContextWindow(messages.length * 100, 200_000)
      if (isNearLimit(ctxWindow)) {
        yield* _(Effect.fail({ _tag: "ContextOverflow", tokens: ctxWindow.tokens } as LoopError))
      }

      // 1. LLM 生成
      const reply = yield* _(llm.complete(messages))

      // 2. 工具调用
      if (reply.toolCalls && reply.toolCalls.length > 0) {
        for (const call of reply.toolCalls) {
          // [G-3] Owner 离线策略
          const ownerCheck = yield* _(
            guard.checkOwnerOnline({
              toolId: call.name,
              category: "write",
            }),
          )
          if (ownerCheck.decision === "deny") {
            yield* _(
              Effect.fail({
                _tag: "GuardRejected",
                reason: { _tag: "OwnerOffline", action: call.name },
              } as LoopError),
            )
          }
          if (ownerCheck.decision === "queue") {
            yield* _(interrupt.awaitExternal("Owner 上线后批准", 24 * 3600 * 1000))
          }

          // [G-2] 承重代码防护
          if (call.name === "write_file" || call.name === "delete_file") {
            const path = (call.input as Record<string, unknown>).path as string
            const lbCheck = yield* _(
              guard.checkLoadBearing(path, call.name === "delete_file" ? "delete" : "write"),
            )
            if (!lbCheck.allowed) {
              yield* _(
                Effect.fail({
                  _tag: "GuardRejected",
                  reason: { _tag: "LoadBearingTouched", path },
                } as LoopError),
              )
            }
          }

          // 执行工具
          const toolCall: ToolCall = {
            id: call.id,
            toolId: call.name as ToolCall["toolId"],
            input: call.input,
            traceId: `${input.conversationId}-${iteration}`,
          }
          const result = yield* _(toolExec.execute(toolCall))
          messages = [
            ...messages,
            {
              id: `${call.id}-result`,
              conversationId: input.conversationId,
              role: "tool" as const,
              content: JSON.stringify(result.output),
              toolCallId: call.id,
              createdAt: Date.now(),
            },
          ]
        }
      } else if (isComplete(reply)) {
        // 3. 完成：签发 IntentReceipt [G-1]
        const evidenceFiles = collectEvidenceFiles(messages)
        const locDelta = computeLocDelta(messages)

        const receipt = yield* _(
          guard.issueReceipt({
            intent: input.userMessage,
            evidenceFiles,
            locDelta,
            authorAgent: "claude-3-5-sonnet",
          }),
        )

        // [G-7] 角色分离
        const reviewer = "claude-3-5-haiku"
        const roleCheck = yield* _(guard.checkRoleSeparation(receipt.authorAgent, reviewer))
        if (!roleCheck.ok) {
          yield* _(
            Effect.fail({
              _tag: "GuardRejected",
              reason: {
                _tag: "RoleConflict",
                author: receipt.authorAgent,
                reviewer,
              },
            } as LoopError),
          )
        }

        return { ...receipt, reviewerAgent: reviewer }
      } else {
        messages = [...messages, reply]
      }
    }

    // 超过最大迭代次数
    return yield* _(
      Effect.fail({
        _tag: "ContextOverflow",
        tokens: messages.length * 100,
      } as LoopError),
    )
  })

// 守卫拒绝错误（用于类型标注）
type GuardRejectedError = LoopError & { readonly _tag: "GuardRejected" }

// ─── Mock LLM Layer（Phase 1 测试用） ────────────────────
export const MockLLMLive = Layer.succeed(
  LLMService,
  LLMService.of({
    complete: (messages) =>
      Effect.sync(() => {
        const lastMsg = messages[messages.length - 1]
        const content = typeof lastMsg?.content === "string" ? lastMsg.content : ""
        return {
          id: `reply-${Date.now()}`,
          conversationId: lastMsg?.conversationId ?? ("mock" as ConversationId),
          role: "assistant" as const,
          content: `[Mock] Received: ${content.slice(0, 50)}... Task complete.`,
          createdAt: Date.now(),
        }
      }),
    stream: () => {
      throw new Error("Mock LLM does not support streaming")
    },
  }),
)

// ─── Mock ToolExecutor Layer（Phase 1 测试用） ───────────
export const MockToolExecutorLive = Layer.succeed(
  ToolExecutor,
  ToolExecutor.of({
    execute: (call) =>
      Effect.succeed({
        toolCallId: call.id,
        success: true,
        output: { path: `mock-${call.toolId}`, locDelta: { added: 10, removed: 0 } },
        durationMs: 5,
      }),
  }),
)

// ─── Mock GuardService Layer（Phase 1 测试用） ───────────
export const MockGuardServiceLive = Layer.succeed(
  GuardService,
  GuardService.of({
    issueReceipt: (input) =>
      Effect.succeed({
        id: `receipt-${Date.now()}`,
        intent: input.intent,
        evidenceFiles: input.evidenceFiles,
        locDelta: input.locDelta,
        chainCompleteness: 1,
        guardFindings: [],
        authorAgent: input.authorAgent,
        createdAt: Date.now(),
      }),
    checkLoadBearing: () => Effect.succeed({ allowed: true }),
    checkOwnerOnline: () => Effect.succeed({ decision: "allow" as const, reason: "online" }),
    verifyHumanSig: () => Effect.succeed(true),
    verifyChain: () => Effect.succeed({ completeness: 1, missing: [] }),
    pickVerification: () => Effect.succeed("Fast" as const),
    checkRoleSeparation: () => Effect.succeed({ ok: true }),
    heal: (effect) => effect,
    archiveAntiPattern: () => Effect.void,
    scheduleChaos: () => Effect.void,
    loadContract: () =>
      Effect.succeed({
        loadedFiles: ["AGENTS.md", ".cursorrules"],
        rules: [],
        loadedAt: Date.now(),
      }),
  }),
)

// ─── Mock LoopInterrupt Layer（Phase 1 测试用） ──────────
export const MockLoopInterruptLive = Layer.succeed(
  LoopInterrupt,
  LoopInterrupt.of({
    interrupt: () => Effect.void,
    resume: () => Effect.void,
    awaitExternal: <A>(): Effect.Effect<A, LoopError> =>
      Effect.fail({ _tag: "OwnerOfflineTimeout", since: Date.now() } as LoopError),
  }),
)

// ─── Mock EventStore Layer（Phase 1 测试用） ─────────────
export const MockEventStoreLive = Layer.succeed(
  EventStoreService,
  EventStoreService.of({
    append: () => Effect.void,
    load: () => Effect.succeed([]),
    subscribe: () => Stream.empty,
  }),
)
