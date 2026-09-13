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
import { makeToolExecutor, toolTimeoutMs } from "./tool-boundary.js"
import { resolveOwnerSubject } from "./tool-boundary-helpers.js"
import { isPendingApprovalOutcome, toRunResult } from "./approval-resume.js"
import { ActiveMainRunConflict, RunPauseForApproval } from "@butler/runtime/run-engine.js"
import {
  pickLLMForRole,
  type LLMAdapter,
  type LLMMessage,
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
 * D58 T5 (audit #3 F-18): map an ActiveMainRunConflict status token to
 * owner-facing Chinese wording. The owner never sees internal state
 * names like "waiting_approval" — only human-readable phrasing.
 */
export function activeRunConflictReply(status: string, runId: string): string {
  switch (status) {
    case "waiting_approval":
      return "当前对话仍有未完成的审批步骤。请回复「确认」或「拒绝」继续，或等待你之前的请求结束。"
    case "waiting_external":
      return "当前对话正在等待外部步骤完成（例如网络命令或审批回执）。稍后再试即可。"
    default:
      return `当前对话已有进行中的 Run（${runId}），请稍后再试。`
  }
}

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

  // P2 fix 2026-09-04: spam guard before LLM call. Catches:
  //   - very long messages (> MAX_SPAM_CHARS)
  //   - heavily repeated tokens (> REPEAT_TOKEN_THRESHOLD occurrences of one token)
  //   - high emoji ratio (> EMOJI_RATIO_MAX of chars are emoji)
  // Returns a short stub reply with no LLM call. Owner can reply with a
  // concrete request to retry.
  const spam = detectSpam(args.content)
  if (spam) {
    return {
      reply: spam,
      iterations: 0,
      toolCalls: 0,
      finalDecision: "Respond",
      traces: ["spam-guard: short-circuited LLM call"],
    }
  }

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
          // D58 T5 (audit #1 F-01): EVAL_DEBUG path used to substitute the
          // string "(undefined)" into a number field when llmTimeoutMs was
          // unset, silently corrupting the timeout value. Only forward
          // the field when EVAL_DEBUG is set AND a real number is available.
          ...(process.env["EVAL_DEBUG"] && args.llmTimeoutMs !== undefined
            ? { llmTimeoutMs: args.llmTimeoutMs }
            : {}),
        }),
    )
  } catch (err) {
    if (err instanceof ActiveMainRunConflict) {
      // D59 T3 (audit #3 F-01): the helper activeRunConflictReply already
      // returns an owner-facing message per status; previously the
      // computed value was discarded and the catch always replied with a
      // hardcoded message that leaked internal status tokens
      // (waiting_approval / waiting_external). Use the helper's reply
      // verbatim — falls back to the generic waiting run message when
      // status is unknown.
      const waitingStatus = activeRunConflictReply(err.activeRun.status, err.activeRun.id)
      const knownStatuses = new Set(["waiting_approval", "waiting_external"])
      const reply = knownStatuses.has(err.activeRun.status)
        ? waitingStatus
        : `当前对话已有进行中的 Run（${err.activeRun.id}），请稍后再试。`
      return {
        reply,
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

  const base = buildWechatInboundMessages(args.content, env, {
    includeExecTools,
    fromUserId: args.fromUserId,
  })
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
        const llmStartedAt = Date.now()
        // D24: pricing lookup is best-effort; missing pricing leaves
        // costUsd as null (aligned with the field's "unknown" semantics).
        const pricing = parseLlmPricing(env)
        const currentModel = resolveCurrentLlmModel(env)
        return Effect.runPromise(
          adapter.complete(msgs, { tools: toolsForLlm }).pipe(
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
            // D59 T3 (audit #3 F-08): drop the stepId UUID from the
            // owner-facing reply (same fix as approval-resume.ts F-06).
            // stepId stays in the trace below for §14 observability.
            reply: `${outcome.reason}\n回复「确认」批准，或「拒绝」取消。`,
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

// ============================================================================
// Spam guard (P2 fix 2026-09-04)
// ============================================================================

const MAX_SPAM_CHARS = 2000
const REPEAT_TOKEN_THRESHOLD = 30
const EMOJI_RATIO_MAX = 0.6

// P2 batch v2 (2026-09-08): 多信号 spam 护栏
const MIN_LINE_REPEAT_TOTAL = 10
const LINE_REPEAT_RATIO_MAX = 0.3

const MIN_TOKEN_REPEAT_TOTAL = 10
const TOKEN_REPEAT_THRESHOLD = 20
const TOKEN_REPEAT_RATIO_MAX = 0.3

const STRUCTURE_MIN_LEN = 1500
const STRUCTURE_MAX_LEN = 2000
const STRUCTURE_PUNCT_RATIO_MAX = 0.005
const STRUCTURE_PUNCT_REGEX = /[。，！？；：、,.!?;:]/

/**
 * Cheap heuristic spam detection before invoking the LLM. Returns a short
 * user-facing reply when the input is suspicious, or null when it looks
 * normal. False positives are acceptable: the owner can re-send a concrete
 * request. False negatives are acceptable too: LLM still has the existing
 * fixture-exhausted / decode-fail safety nets downstream.
 */
function detectSpam(content: string): string | null {
  if (content.length === 0) return null
  if (content.length > MAX_SPAM_CHARS) {
    return `消息过长（${content.length} 字符，上限 ${MAX_SPAM_CHARS}）。请发具体需求。`
  }
  // Repeated character: CJK content has no whitespace, so per-token
  // counting is unreliable. Count per-character frequency and flag if
  // any single char appears > REPEAT_TOKEN_THRESHOLD times AND dominates
  // (>= 30% of total length). Catches "请帮我请帮我请帮我..." style spam
  // while not flagging legitimate long Chinese messages.
  if (content.length >= 50) {
    const charCounts = new Map<string, number>()
    for (const ch of content) charCounts.set(ch, (charCounts.get(ch) ?? 0) + 1)
    let maxChar = ""
    let maxCount = 0
    for (const [c, n] of charCounts) {
      if (n > maxCount) {
        maxCount = n
        maxChar = c
      }
    }
    if (maxCount > REPEAT_TOKEN_THRESHOLD && maxCount / content.length >= 0.3) {
      return `检测到字符「${maxChar}」重复 ${maxCount} 次。请发具体需求。`
    }
  }
  // Emoji ratio: count chars in emoji/symbol ranges.
  let emojiCount = 0
  for (const ch of content) {
    const code = ch.codePointAt(0) ?? 0
    if (code >= 0x1f000 && code <= 0x1ffff) emojiCount += 1
  }
  if (content.length >= 20 && emojiCount / content.length > EMOJI_RATIO_MAX) {
    return `检测到 emoji 占比 ${Math.round((emojiCount / content.length) * 100)}%。请发具体需求。`
  }

  // F3: Per-line 重复（多行短行重复）
  if (content.length >= 100) {
    const lines = content.split(/\r?\n/).filter((l) => l.length > 0)
    if (lines.length >= MIN_LINE_REPEAT_TOTAL) {
      const unique = new Set(lines)
      if (unique.size / lines.length < LINE_REPEAT_RATIO_MAX) {
        return `检测到 ${lines.length} 行中只有 ${unique.size} 种，疑似重复内容。请发具体需求。`
      }
    }
  }

  // F4: Whitespace-token 重复（多字 token 间空格/换行重复）
  if (content.length >= 50) {
    const tokens = content.split(/\s+/).filter((t) => t.length > 0)
    if (tokens.length >= MIN_TOKEN_REPEAT_TOTAL) {
      const counts = new Map<string, number>()
      for (const t of tokens) counts.set(t, (counts.get(t) ?? 0) + 1)
      let maxToken = ""
      let maxCount = 0
      for (const [t, n] of counts) {
        if (n > maxCount) {
          maxCount = n
          maxToken = t
        }
      }
      if (
        maxCount > TOKEN_REPEAT_THRESHOLD &&
        maxCount / tokens.length >= TOKEN_REPEAT_RATIO_MAX
      ) {
        const display =
          maxToken.length > 20 ? `${maxToken.slice(0, 20)}...` : maxToken
        return `检测到 token「${display}」重复 ${maxCount} 次。请发具体需求。`
      }
    }
  }

  // F5: Length+structure（1500-2000 字符无标点无换行）
  if (content.length > STRUCTURE_MIN_LEN && content.length <= STRUCTURE_MAX_LEN) {
    const hasNewline = content.includes("\n")
    let punctCount = 0
    for (const ch of content) if (STRUCTURE_PUNCT_REGEX.test(ch)) punctCount += 1
    if (!hasNewline && punctCount / content.length < STRUCTURE_PUNCT_RATIO_MAX) {
      return `消息结构异常（${content.length} 字符无标点无换行）。请分批发送或简化需求。`
    }
  }

  return null
}
