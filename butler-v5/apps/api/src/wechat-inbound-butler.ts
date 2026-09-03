import { Effect } from "effect"
import type { EventBridge } from "@butler/persistence/event-bridge.js"
import type { WorkingSetResult } from "@butler/runtime/working-set.js"
import { AgentKernel } from "@butler/runtime/agent-kernel.js"
import type { ModelDecision } from "@butler/runtime/decision.js"
import { getSharedLocalTracer } from "@butler/runtime/observability/local-tracer.js"
import {
  computeCostUsd,
  parseLlmPricing,
  resolveCurrentLlmModel,
} from "./llm-pricing.js"
import {
  DEFAULT_MAX_LOOP_ITERATIONS,
  runConversationLoop,
  type ConversationLoopMessage,
  type ConversationLoopResult,
} from "@butler/runtime/execution/index.js"
import { type ToolDefinition } from "@butler/runtime/tool-runtime.js"
import { resolveReadModelSource } from "@butler/domain"
import {
  buildWechatRunTrigger,
  validateRunTrigger,
  type RunTrigger,
} from "@butler/domain/runtime.js"
import type { Wiring } from "./wiring.js"
import { findTool, llmToolsForButler, makeWeibutlerTools } from "./tools.js"
import { makeToolExecutor, resolveOwnerSubject, toolTimeoutMs } from "./tool-boundary.js"
import { isPendingApprovalOutcome, toRunResult } from "./approval-resume.js"
import { ActiveMainRunConflict, RunPauseForApproval } from "@butler/runtime/run-engine.js"
import {
  pickLLMForRole,
  type LLMAdapter,
  type LLMMessage,
  type LLMTool,
} from "@butler/adapters"
import { buildWechatInboundMessages, stubReply } from "./wechat-inbound-llm.js"
import { isExecCapability } from "./wechat-tool-profile.js"
import {
  compactConversationHistoryWithLlm,
  eventsToHistoryMessages,
} from "./conversation-memory.js"
import { tryWechatInlineApproval } from "./wechat-inline-approval.js"
import { loadDurableMemorySystemPrefix } from "./durable-memory-inject.js"
import { loadProjectKnowledgeSystemPrefix } from "./project-knowledge-inject.js"
import { resolveWechatAllowedToolNames } from "./wechat-tool-allowlist.js"

/**
 * Logger surface for the butler loop. Mirrors the LLMReplyLogger
 * shape from R8.x.2 so the same operator-debug story applies.
 */
export interface ButlerLoopLogger {
  warn: (message: string, extra?: unknown) => void
  error: (message: string, error: unknown) => void
}

const defaultLogger: ButlerLoopLogger = {
  warn: (message, extra) => {
    // eslint-disable-next-line no-console -- intentional stderr log for operator debugging
    console.warn(message, extra ?? "")
  },
  error: (message, error) => {
    // eslint-disable-next-line no-console -- intentional stderr log for operator debugging
    console.error(message, error)
  },
}

/**
 * Result of a single butler loop run. Alias of Execution ConversationLoopResult.
 */
export type ButlerLoopResult = ConversationLoopResult

/**
 * Delivery-shell entry: Intake already normalized; this wires WeChat-specific
 * tools/LLM/history then runs Execution `runConversationLoop` under RunEngine.
 */
export async function runButlerLoop(args: {
  readonly wiring: Wiring
  readonly conversationId: string
  readonly content: string
  readonly fromUserId: string
  readonly projectId: string
  readonly idempotencyKey?: string
  readonly runTrigger?: RunTrigger
  readonly budget?: Readonly<Record<string, unknown>>
  readonly deadline?: Date | null
  readonly goal?: string
  /** When set, only these tool names are exposed to the model. */
  readonly allowedToolNames?: readonly string[]
  readonly env?: NodeJS.ProcessEnv
  readonly logger?: ButlerLoopLogger
  readonly adapter?: LLMAdapter
  /** Override per-LLM-call timeout (ms). Default reads BUTLER_V5_LLM_TIMEOUT_MS
   *  from env. Used by eval scenario 16 to test the timeout path. */
  readonly llmTimeoutMs?: number
}): Promise<ButlerLoopResult> {
  const env = args.env ?? process.env
  const inline = await tryWechatInlineApproval({
    wiring: args.wiring,
    conversationId: args.conversationId,
    content: args.content,
    fromUserId: args.fromUserId,
    env,
  })
  if (inline) return inline

  const readModel = resolveReadModelSource(env)
  if (readModel !== "event_store") {
    const existing = await args.wiring.runtimeStore.listMessages(args.conversationId)
    if (existing.length === 0) {
      await args.wiring.backfillConversation(args.conversationId)
    }
  }
  const idempotencyKey =
    args.idempotencyKey ?? `wechat-${args.conversationId}-${args.content.length}-${Date.now()}`
  const trigger =
    args.runTrigger ??
    buildWechatRunTrigger({
      userId: args.fromUserId,
      conversationId: args.conversationId,
      content: args.content,
      messageId: idempotencyKey,
    })
  const validated = validateRunTrigger(trigger)
  if (!validated.ok) {
    throw new Error(`invalid RunTrigger: ${validated.reason}`)
  }
  const allowedToolNames =
    args.allowedToolNames ??
    resolveWechatAllowedToolNames({
      projectId: args.projectId,
      env,
      mcpBundle: args.wiring.mcp,
    })
  try {
    return await args.wiring.runEngine.executeInbound(
      {
        conversationId: args.conversationId,
        messageId: crypto.randomUUID(),
        subject: trigger.subject,
        content: args.content,
        idempotencyKey,
        trigger,
        projectId: args.projectId,
        ...(args.goal ? { goal: args.goal } : {}),
        ...(args.budget ? { budget: args.budget } : {}),
        ...(args.deadline !== undefined ? { deadline: args.deadline } : {}),
      },
      async (ctx) =>
        runButlerLoopBody({
          ...args,
          allowedToolNames,
          runId: ctx.runId,
          workingSet: ctx.workingSet,
          ...(process.env["EVAL_DEBUG"] ? { llmTimeoutMs: args.llmTimeoutMs ?? "(undefined)" as unknown as number } : {}),
        }),
    )
  } catch (err) {
    if (err instanceof ActiveMainRunConflict) {
      const waiting =
        err.activeRun.status === "waiting_approval" || err.activeRun.status === "waiting_external"
      return {
        reply: waiting
          ? `当前对话仍有未完成的 Run（${err.activeRun.status}）。请先回复「确认」或「拒绝」完成审批，或等待外部步骤结束。`
          : `当前对话已有进行中的 Run（${err.activeRun.id}），请稍后再试。`,
        iterations: 0,
        toolCalls: 0,
        finalDecision: "Finish",
        traces: [`active-main-run-conflict: ${err.activeRun.id} ${err.activeRun.status}`],
      }
    }
    const msg = err instanceof Error ? err.message : String(err)
    const logger = args.logger ?? defaultLogger
    logger.error("butler-loop failed; responding with degraded reply", err)
    return {
      reply: `这次没处理成功，请稍后再发一次。若反复如此，请联系管理员处理。`,
      iterations: 0,
      toolCalls: 0,
      finalDecision: "Finish",
      traces: [`loop-error: ${msg}`],
    }
  }
}

async function persistAssistantReply(args: {
  readonly wiring: Wiring
  readonly conversationId: string
  readonly content: string
  readonly idempotencyKey: string
}): Promise<void> {
  try {
    await args.wiring.runtimeStore.appendMessage({
      messageId: crypto.randomUUID(),
      conversationId: args.conversationId,
      role: "assistant",
      content: { text: args.content },
      triggerSource: "channel",
      idempotencyKey: args.idempotencyKey,
      createdAt: new Date(),
    })
  } catch {
    // compat path must not break the wechat reply contract
  }
}

async function runButlerLoopBody(args: {
  readonly wiring: Wiring
  readonly conversationId: string
  readonly content: string
  readonly fromUserId: string
  readonly projectId: string
  readonly runId: string
  readonly workingSet: WorkingSetResult
  readonly allowedToolNames?: readonly string[]
  readonly env?: NodeJS.ProcessEnv
  readonly logger?: ButlerLoopLogger
  readonly adapter?: LLMAdapter
  /** Override per-LLM-call timeout (ms). Default reads BUTLER_V5_LLM_TIMEOUT_MS
   *  from env (else 30_000). Used by eval scenario 16 to test timeout path. */
  readonly llmTimeoutMs?: number
  /** Override stuck-loop threshold (Phase D fix B-06). Default reads
   *  BUTLER_V5_STUCK_LOOP_THRESHOLD from env (else 3). */
  readonly stuckLoopThreshold?: number
  /** Override max-decode-retries (Phase D fix B-08/10). Default reads
   *  BUTLER_V5_MAX_DECODE_RETRIES from env (else 1). */
  readonly maxDecodeRetries?: number
}): Promise<ButlerLoopResult> {
  const env = args.env ?? process.env
  const logger = args.logger ?? defaultLogger
  const bridge: EventBridge = args.wiring.eventBridge

  const kernel = new AgentKernel({
    bridge,
    conversationId: args.conversationId,
    projectId: args.projectId,
    actor: { kind: "agent", id: "wechat-butler-v5" },
  })

  const userMessage = { role: "user" as const, content: args.content }
  try {
    await kernel.openTurn({ userMessage })
  } catch (err) {
    logger.error("[v5-butler-loop] openTurn failed:", err)
    return {
      reply: stubReply(args.content, args.fromUserId, args.projectId),
      iterations: 0,
      toolCalls: 0,
      finalDecision: "Finish",
      traces: ["openTurn failed; returned stub"],
    }
  }

  const allow = args.allowedToolNames ? new Set(args.allowedToolNames) : null
  const includeExecTools =
    allow !== null && [...allow].some((name) => isExecCapability(name))

  const base = buildWechatInboundMessages(args.content, env, { includeExecTools })
  const systemMsg = base[0]
  const userMsg = base[1]
  let historyTurns: LLMMessage[] = []
  try {
    const events = await bridge.loadStream(args.conversationId)
    historyTurns = [...eventsToHistoryMessages(events, { currentUserContent: args.content })]
  } catch (err) {
    logger.warn(
      "[v5-butler-loop] loadStream for history failed; continuing without memory:",
      err instanceof Error ? err.message : String(err),
    )
  }

  const memorySubject = resolveOwnerSubject(env, args.fromUserId)
  const tools: readonly ToolDefinition[] = makeWeibutlerTools({
    bridge,
    conversationId: args.conversationId,
    actor: { kind: "agent", id: "wechat-butler-v5" },
    wechatUserId: args.fromUserId,
    runtimeStore: args.wiring.runtimeStore,
    runId: args.runId,
    env,
    mcpBundle: args.wiring.mcp,
    durableMemoryStore: args.wiring.durableMemoryStore,
    documentStore: args.wiring.documentStore,
    projectKnowledgeStore: args.wiring.projectKnowledgeStore,
    memorySubject,
    projectId: args.projectId,
    // D5-arch-align §20 #5 (opt-in): ButlerToolContext exposes
    // `parentAllowedToolNames` so a future commit can derive parent's
    // capability grant chain and pass it as `parentAllowlist`. We do NOT
    // auto-pass it from the LLM tool allowlist here: plan-mode parents
    // delegate to dev-mode children via a separate grant chain
    // (dev-session-grant.ts), not via the LLM tool set.
    parentAllowedToolNames: undefined,
  }).filter((t) => (allow ? allow.has(t.name as string) : true))
  const llmTools = llmToolsForButler({ env, mcpBundle: args.wiring.mcp }).filter((t) =>
    allow ? allow.has(t.name) : true,
  )

  const toolExecutor = makeToolExecutor({
    tools,
    store: args.wiring.runtimeStore,
    runId: args.runId,
    ownerSubject: resolveOwnerSubject(env, args.fromUserId),
    subject: args.fromUserId,
    conversationId: args.conversationId,
    timeoutMsFor: toolTimeoutMs,
    wechatUserId: args.fromUserId,
    mcpServerIdByCapability: args.wiring.mcp.serverIdByCapability,
  })

  const adapter = args.adapter ?? pickLLMForRole(env, "plan")
  if (!adapter) {
    try {
      await kernel.applyDecision({ _tag: "Finish", reason: "no LLM configured" })
    } catch {
      // ignore
    }
    return {
      reply: stubReply(args.content, args.fromUserId, args.projectId),
      iterations: 0,
      toolCalls: 0,
      finalDecision: "Finish",
      traces: ["no LLM configured; returned stub"],
    }
  }

  const relationalHistory = args.workingSet.messages.filter(
    (m) => m.role === "user" || m.role === "assistant" || m.role === "system",
  )
  const useRelationalHistory =
    relationalHistory.length > 1 ||
    (relationalHistory.length === 1 && relationalHistory[0]?.role !== "user")

  let historyMessages: LLMMessage[]
  let eventStoreCompactSource: "none" | "extractive" | "llm" = "none"
  if (useRelationalHistory) {
    historyMessages = relationalHistory.filter(
      (m) => !(m.role === "user" && m.content === args.content.trim()),
    )
  } else {
    const compact = await compactConversationHistoryWithLlm(historyTurns, { adapter })
    historyMessages = [...compact.messages]
    eventStoreCompactSource = compact.source
  }

  const messages: ConversationLoopMessage[] = []
  if (systemMsg) messages.push({ role: systemMsg.role, content: systemMsg.content })
  const memoryPrefix = await loadDurableMemorySystemPrefix({
    store: args.wiring.durableMemoryStore,
    subject: memorySubject,
    query: args.content,
    env,
  })
  if (memoryPrefix) {
    messages.push({ role: "system", content: memoryPrefix })
  }
  const projectKnowledgePrefix = await loadProjectKnowledgeSystemPrefix({
    store: args.wiring.projectKnowledgeStore,
    projectId: args.projectId,
    query: args.content,
    env,
  })
  if (projectKnowledgePrefix) {
    messages.push({ role: "system", content: projectKnowledgePrefix })
  }
  for (const m of historyMessages) {
    messages.push({
      role: m.role,
      content: m.content,
      ...(m.toolCalls ? { toolCalls: m.toolCalls } : {}),
      ...(m.toolCallId ? { toolCallId: m.toolCallId } : {}),
      ...(m.toolName ? { toolName: m.toolName } : {}),
    })
  }
  if (userMsg) messages.push({ role: userMsg.role, content: userMsg.content })

  const initialTraces: string[] = []
  if (memoryPrefix) {
    initialTraces.push("durable-memory: injected confirmed prefix")
  }
  if (projectKnowledgePrefix) {
    initialTraces.push("project-knowledge: injected working-set prefix")
  }
  if (historyMessages.length > 0) {
    if (useRelationalHistory) {
      initialTraces.push(
        `history: ${historyMessages.length} msgs source=relational:${args.workingSet.source}`,
      )
    } else {
      initialTraces.push(
        `history: ${historyMessages.length} msgs source=event_store compacted=${eventStoreCompactSource}`,
      )
    }
  }

  return runConversationLoop({
    kernel,
    messages,
    llmTools,
    maxIterations: DEFAULT_MAX_LOOP_ITERATIONS,
    initialTraces,
    ...(args.llmTimeoutMs !== undefined ? { llmTimeoutMs: args.llmTimeoutMs } : {}),
    ...(args.stuckLoopThreshold !== undefined ? { stuckLoopThreshold: args.stuckLoopThreshold } : {}),
    ...(args.maxDecodeRetries !== undefined ? { maxDecodeRetries: args.maxDecodeRetries } : {}),
    ports: {
      logger,
      stubReply: () => stubReply(args.content, args.fromUserId, args.projectId),
      findTool: (name) => findTool(tools, name),
      persistAssistantReply: async (content) => {
        await persistAssistantReply({
          wiring: args.wiring,
          conversationId: args.conversationId,
          content,
          idempotencyKey: `assistant:${args.conversationId}:${Date.now()}`,
        })
      },
      complete: async (msgs, toolsForLlm) => {
        const llmMessages = msgs as unknown as LLMMessage[]
        const llmStartedAt = Date.now()
        // D24: pricing lookup is best-effort; missing pricing leaves
        // costUsd as null (aligned with the field's "unknown" semantics).
        const pricing = parseLlmPricing(env)
        const currentModel = resolveCurrentLlmModel(env)
        return Effect.runPromise(
          adapter.complete(llmMessages, { tools: toolsForLlm as unknown as readonly LLMTool[] }).pipe(
            Effect.match({
              onFailure: (err) => {
                // D23: error trace (no usage when the call never reached the model).
                const tracer = getSharedLocalTracer()
                tracer.record({
                  kind: "step",
                  name: "llm_call",
                  status: "error",
                  conversationId: args.conversationId,
                  runId: args.runId,
                  subject: memorySubject,
                  durationMs: Date.now() - llmStartedAt,
                  detail: { reason: err instanceof Error ? err.message : String(err) },
                })
                return {
                  ok: false as const,
                  reason: err instanceof Error ? err.message : String(err),
                }
              },
              onSuccess: (resp) => {
                // D23: success trace carries first-class `token` so §14
                // observability captures input / output / total tokens per
                // LLM call. D24: fills `costUsd` when env-driven pricing
                // for the current model is available; otherwise null.
                const tracer = getSharedLocalTracer()
                const costUsd =
                  resp.usage !== undefined && currentModel !== null
                    ? computeCostUsd(resp.usage, currentModel, pricing)
                    : null
                tracer.record({
                  kind: "step",
                  name: "llm_call",
                  status: "ok",
                  conversationId: args.conversationId,
                  runId: args.runId,
                  subject: memorySubject,
                  durationMs: Date.now() - llmStartedAt,
                  ...(resp.usage !== undefined ? { token: resp.usage } : {}),
                  costUsd,
                })
                return {
                  ok: true as const,
                  response: {
                    content: resp.content,
                    toolCalls: resp.toolCalls,
                    ...(resp.usage !== undefined ? { usage: resp.usage } : {}),
                  },
                }
              },
            }),
          ),
        )
      },
      executeTool: async (def, toolArgs) => {
        const outcome = await toolExecutor.execute(def, toolArgs)
        if (isPendingApprovalOutcome(outcome)) {
          throw new RunPauseForApproval({
            reply: `${outcome.reason}\n审批编号: ${outcome.pendingApproval.stepId}\n回复「确认」批准，或「拒绝」取消。`,
            iterations: 0,
            toolCalls: 0,
            finalDecision: "WaitForApproval" as ModelDecision["_tag"],
            traces: [
              `waiting approval ${outcome.pendingApproval.stepId} for ${String(def.name)}`,
            ],
          } satisfies ButlerLoopResult)
        }
        return toRunResult(outcome)
      },
    },
  })
}
