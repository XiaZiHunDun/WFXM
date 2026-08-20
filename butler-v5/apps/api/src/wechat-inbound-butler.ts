import { Effect } from "effect"
import type { EventBridge } from "@butler/runtime/bridge.js"
import type { WorkingSetResult } from "@butler/runtime/working-set.js"
import { AgentKernel } from "@butler/runtime/agent-kernel.js"
import { decodeDecision, type ModelDecision } from "@butler/runtime/decision.js"
import { runTool, type ToolDefinition } from "@butler/runtime/tool-runtime.js"
import { resolveReadModelSource } from "@butler/domain"
import type { Wiring } from "./wiring.js"
import { findTool, makeWeibutlerTools, WEIBUTLER_LLM_TOOLS } from "./tools.js"
import {
  pickLLMProvider,
  type LLMAdapter,
  type LLMAssistantResponse,
  type LLMMessage,
} from "@butler/adapters"
import { buildWechatInboundMessages, stubReply } from "./wechat-inbound-llm.js"
import {
  compactConversationHistoryWithLlm,
  eventsToHistoryMessages,
} from "./conversation-memory.js"

/**
 * Maximum tool-call iterations per inbound turn. Bounds the loop so a
 * chatty model cannot drive v5 into runaway tool use; on overrun the
 * loop returns the stub reply (v4 contract preserved).
 */
const MAX_LOOP_ITERATIONS = 5

/**
 * Per-tool wall-clock budget. Each tool execution is wrapped in
 * runTool with this timeout — slow tools do not stall the route.
 */
const TOOL_TIMEOUT_MS = 5000
const SEND_WECHAT_FILE_TIMEOUT_MS = 120_000

export function toolTimeoutMs(toolName: string): number {
  return toolName === "send_wechat_file" ? SEND_WECHAT_FILE_TIMEOUT_MS : TOOL_TIMEOUT_MS
}

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
 * Result of a single butler loop run. The route returns `reply` to
 * the wechat caller and logs `traces` for operator debugging.
 */
export interface ButlerLoopResult {
  readonly reply: string
  readonly iterations: number
  readonly toolCalls: number
  readonly finalDecision: ModelDecision["_tag"]
  readonly traces: readonly string[]
}

/**
 * Tool call trace entry — captured for the operator log so a
 * postmortem can see which tools ran during a turn.
 */
interface ToolTrace {
  readonly iteration: number
  readonly toolName: string
  readonly ok: boolean
  readonly summary: string
}

/**
 * Run the full AgentKernel-backed butler loop for one wechat
 * inbound turn. Replaces R8.x.2's synchronous LLM call with a real
 * state machine + tool execution, while preserving the v4 → v5 → v4
 * contract (always returns a non-empty `reply`).
 *
 * The loop (R8.x.4: native tool_calls):
 *  1. Open a turn on a fresh AgentKernel (records TurnOpened).
 *  2. Build messages (system + recent history + current user msg).
 *  3. Call the LLM with the wechat tool set.
 *  4. If the response carries native tool_calls (R8.x.4):
 *     - push the assistant message back (with toolCalls preserved)
 *     - run each tool, push a tool-result message
 *     - loop back to step 3
 *  5. If the response is text-only:
 *     - try `decodeDecision(content)` for the JSON-decision protocol
 *       (legacy / models without native tool support)
 *     - if it parses, apply the ModelDecision
 *     - else treat the raw text as a Respond (best-effort)
 *  6. Bound by MAX_LOOP_ITERATIONS; on overrun, fall back to the stub
 *     reply (the v4 contract is preserved).
 */
export async function runButlerLoop(args: {
  readonly wiring: Wiring
  readonly conversationId: string
  readonly content: string
  readonly fromUserId: string
  readonly projectId: string
  readonly idempotencyKey?: string
  readonly env?: NodeJS.ProcessEnv
  readonly logger?: ButlerLoopLogger
  readonly adapter?: LLMAdapter
}): Promise<ButlerLoopResult> {
  const env = args.env ?? process.env
  const readModel = resolveReadModelSource(env)
  if (readModel !== "event_store") {
    await args.wiring.backfillConversation(args.conversationId)
  }
  const idempotencyKey =
    args.idempotencyKey ?? `wechat-${args.conversationId}-${args.content.length}-${Date.now()}`
  return args.wiring.runEngine.executeInbound(
    {
      conversationId: args.conversationId,
      messageId: crypto.randomUUID(),
      subject: args.fromUserId,
      content: args.content,
      idempotencyKey,
      triggerSource: "channel",
    },
    async (ctx) => runButlerLoopBody({ ...args, workingSet: ctx.workingSet }),
  )
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
  readonly workingSet: WorkingSetResult
  readonly env?: NodeJS.ProcessEnv
  readonly logger?: ButlerLoopLogger
  readonly adapter?: LLMAdapter
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

  // 1. Open the turn. Kernel records TurnOpened + transitions to
  //    'running'. Failure here means we cannot proceed.
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

  // 2. Load prior turns, then compact (LLM summary when over budget)
  //    after we know the adapter. Current TurnOpened is dropped by
  //    eventsToHistoryMessages.
  const base = buildWechatInboundMessages(args.content)
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

  const tools: readonly ToolDefinition[] = makeWeibutlerTools({
    bridge,
    conversationId: args.conversationId,
    actor: { kind: "agent", id: "wechat-butler-v5" },
    wechatUserId: args.fromUserId,
  })

  const adapter = args.adapter ?? pickLLMProvider(env)
  if (!adapter) {
    await safeApplyDecision(kernel, { _tag: "Finish", reason: "no LLM configured" }, logger)
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

  const messages: LLMMessage[] = []
  if (systemMsg) messages.push({ role: systemMsg.role, content: systemMsg.content })
  messages.push(...historyMessages)
  if (userMsg) messages.push({ role: userMsg.role, content: userMsg.content })

  const traces: string[] = []
  if (historyMessages.length > 0) {
    if (useRelationalHistory) {
      traces.push(
        `history: ${historyMessages.length} msgs source=relational:${args.workingSet.source}`,
      )
    } else {
      traces.push(
        `history: ${historyMessages.length} msgs source=event_store compacted=${eventStoreCompactSource}`,
      )
    }
  }
  let toolCalls = 0
  let lastDecision: ModelDecision["_tag"] = "Finish"

  // 3. Main loop.
  for (let iteration = 0; iteration < MAX_LOOP_ITERATIONS; iteration++) {
    const outcome = await Effect.runPromise(
      adapter.complete(messages, { tools: WEIBUTLER_LLM_TOOLS }).pipe(
        Effect.match({
          onFailure: (err) => {
            logger.error(
              `[v5-butler-loop] LLM call failed (fromUserId=${args.fromUserId}); falling back to stub:`,
              err,
            )
            return {
              ok: false as const,
              reason: err instanceof Error ? err.message : String(err),
            }
          },
          onSuccess: (resp) => ({ ok: true as const, response: resp }),
        }),
      ),
    )

    if (!outcome.ok) {
      // LLM failed — return stub reply, mark kernel complete.
      await safeApplyDecision(
        kernel,
        { _tag: "Finish", reason: `llm failure: ${outcome.reason}` },
        logger,
      )
      return {
        reply: stubReply(args.content, args.fromUserId, args.projectId),
        iterations: iteration + 1,
        toolCalls,
        finalDecision: "Finish",
        traces: [...traces, `llm failure: ${outcome.reason}`],
      }
    }

    const response: LLMAssistantResponse = outcome.response

    // 4. Native tool_calls path (R8.x.4). Echo the assistant message
    //    back (with toolCalls preserved) and queue tool result messages.
    if (response.toolCalls.length > 0) {
      // Persist the assistant turn (tool_use only — text accompanying
      // the tool calls is included in content so the model sees it
      // next iteration).
      messages.push({
        role: "assistant",
        content: response.content,
        toolCalls: response.toolCalls,
      })

      const toolResultMessages: LLMMessage[] = []
      for (const tc of response.toolCalls) {
        const def = findTool(tools, tc.name)
        if (!def) {
          logger.warn(
            `[v5-butler-loop] Unknown tool '${tc.name}' at iteration ${iteration}; pushing error result`,
          )
          traces.push(`unknown tool: ${tc.name}`)
          toolResultMessages.push({
            role: "tool",
            content: `[error] unknown tool: ${tc.name}`,
            toolCallId: tc.id,
            toolName: tc.name,
          })
          continue
        }
        toolCalls += 1
        const toolResult = await runTool(def, tc.args, { timeoutMs: toolTimeoutMs(tc.name) })
        const trace: ToolTrace = {
          iteration,
          toolName: tc.name,
          ok: toolResult.ok,
          summary: toolResult.ok
            ? summarizeForLog(String(toolResult.output))
            : `error: ${toolResult.reason}`,
        }
        traces.push(`${trace.toolName}@${trace.iteration}: ${trace.summary}`)
        toolResultMessages.push({
          role: "tool",
          content: toolResult.ok ? String(toolResult.output) : `[error] ${toolResult.reason}`,
          toolCallId: tc.id,
          toolName: tc.name,
        })
      }
      // Append the tool result messages in order.
      messages.push(...toolResultMessages)
      // Continue the loop — the model will see the tool results and
      // decide whether to call another tool or respond with text.
      continue
    }

    // 5. Text-only path: JSON-decision fallback (legacy R8.x.3
    //    protocol) then plain-text Respond as last resort.
    const raw = response.content.trim()
    const decoded = decodeDecision(raw)
    if (!decoded.ok) {
      logger.warn(
        `[v5-butler-loop] decodeDecision failed at iteration ${iteration}: ${decoded.reason}; treating as Respond`,
      )
      // The model returned plain text rather than JSON. Treat the raw
      // text as a Respond decision so the user still gets a reply.
      const respondDecision: ModelDecision = { _tag: "Respond", content: raw }
      await safeApplyDecision(kernel, respondDecision, logger)
      lastDecision = "Respond"
      return {
        reply: raw || stubReply(args.content, args.fromUserId, args.projectId),
        iterations: iteration + 1,
        toolCalls,
        finalDecision: "Respond",
        traces: [...traces, `decode failed (${decoded.reason}); plain-text reply`],
      }
    }

    const decision = decoded.value
    lastDecision = decision._tag

    switch (decision._tag) {
      case "Respond": {
        await safeApplyDecision(kernel, decision, logger)
        const text = decision.content.trim()
        await persistAssistantReply({
          wiring: args.wiring,
          conversationId: args.conversationId,
          content: text || stubReply(args.content, args.fromUserId, args.projectId),
          idempotencyKey: `assistant:${args.conversationId}:${Date.now()}`,
        })
        return {
          reply: text || stubReply(args.content, args.fromUserId, args.projectId),
          iterations: iteration + 1,
          toolCalls,
          finalDecision: "Respond",
          traces,
        }
      }
      case "Finish": {
        await safeApplyDecision(kernel, decision, logger)
        return {
          reply: stubReply(args.content, args.fromUserId, args.projectId),
          iterations: iteration + 1,
          toolCalls,
          finalDecision: "Finish",
          traces,
        }
      }
      case "AskApproval": {
        // Wechat is one-shot — there is no interactive approval flow.
        // Echo the question back as a Respond-equivalent so the user
        // sees what the model wanted to ask.
        await safeApplyDecision(kernel, decision, logger)
        const text = `[需要确认] ${decision.question}`
        return {
          reply: text,
          iterations: iteration + 1,
          toolCalls,
          finalDecision: "AskApproval",
          traces: [...traces, `AskApproval echoed: ${decision.question}`],
        }
      }
      case "Delegate": {
        // R8.x.6: dispatch via the delegate_to_subagent tool (which
        // wraps delegate-runtime), then loop back so the model can
        // emit a follow-up Respond using the child conversation id.
        // We synthesize a fake assistant(toolCalls) + tool-result
        // pair so the LLM has the outcome in context — same shape
        // the legacy CallTool path uses.
        await safeApplyDecision(kernel, decision, logger)
        const def = findTool(tools, "delegate_to_subagent")
        if (!def) {
          logger.warn(
            `[v5-butler-loop] delegate_to_subagent tool not registered; treating as Finish`,
          )
          traces.push("delegate_to_subagent missing")
          await safeApplyDecision(
            kernel,
            { _tag: "Finish", reason: "delegate_to_subagent missing" },
            logger,
          )
          return {
            reply: stubReply(args.content, args.fromUserId, args.projectId),
            iterations: iteration + 1,
            toolCalls,
            finalDecision: "Delegate",
            traces,
          }
        }
        toolCalls += 1
        const toolResult = await runTool(
          def,
          { task: decision.task, role: decision.role },
          { timeoutMs: TOOL_TIMEOUT_MS },
        )
        const trace: ToolTrace = {
          iteration,
          toolName: "delegate_to_subagent",
          ok: toolResult.ok,
          summary: toolResult.ok
            ? summarizeForLog(String(toolResult.output))
            : `error: ${toolResult.reason}`,
        }
        traces.push(`${trace.toolName}@${trace.iteration}: ${trace.summary}`)
        // Echo the decision as a fake assistant tool_call so the
        // model has structured context for the next iteration.
        const toolCallId = `json-${iteration}-delegate_to_subagent`
        messages.push({
          role: "assistant",
          content: JSON.stringify(decision),
          toolCalls: [
            {
              id: toolCallId,
              name: "delegate_to_subagent",
              args: { task: decision.task, role: decision.role },
            },
          ],
        })
        messages.push({
          role: "tool",
          content: toolResult.ok ? String(toolResult.output) : `[error] ${toolResult.reason}`,
          toolCallId,
          toolName: "delegate_to_subagent",
        })
        continue
      }
      case "CallTool": {
        // R8.x.4: a JSON-decision CallTool is the legacy path. Run
        // the tool, then loop. The model should switch to native
        // tool_calls once available, but we keep this for the
        // JSON-decision protocol.
        await safeApplyDecision(kernel, decision, logger)
        const def = findTool(tools, decision.toolName)
        if (!def) {
          logger.warn(
            `[v5-butler-loop] Unknown tool '${decision.toolName}' at iteration ${iteration}; treating as Finish`,
          )
          traces.push(`unknown tool: ${decision.toolName}`)
          return {
            reply: stubReply(args.content, args.fromUserId, args.projectId),
            iterations: iteration + 1,
            toolCalls,
            finalDecision: "CallTool",
            traces,
          }
        }
        toolCalls += 1
        const toolResult = await runTool(def, decision.args, {
          timeoutMs: toolTimeoutMs(decision.toolName),
        })
        const trace: ToolTrace = {
          iteration,
          toolName: decision.toolName,
          ok: toolResult.ok,
          summary: toolResult.ok
            ? summarizeForLog(String(toolResult.output))
            : `error: ${toolResult.reason}`,
        }
        traces.push(`${trace.toolName}@${trace.iteration}: ${trace.summary}`)
        // Echo the legacy decision as a fake assistant message + tool
        // result so the model has context for the next iteration.
        messages.push({
          role: "assistant",
          content: JSON.stringify(decision),
          toolCalls: [
            {
              id: `json-${iteration}-${decision.toolName}`,
              name: decision.toolName,
              args: decision.args,
            },
          ],
        })
        messages.push({
          role: "tool",
          content: toolResult.ok ? String(toolResult.output) : `[error] ${toolResult.reason}`,
          toolCallId: `json-${iteration}-${decision.toolName}`,
          toolName: decision.toolName,
        })
        continue
      }
      default: {
        const _: never = decision
        void _
        return {
          reply: stubReply(args.content, args.fromUserId, args.projectId),
          iterations: iteration + 1,
          toolCalls,
          finalDecision: "Finish",
          traces,
        }
      }
    }
  }

  // Loop exhausted — fall back to stub reply. Kernel may already be
  // in 'completed' state from a prior iteration, so wrap in try/catch.
  logger.warn(
    `[v5-butler-loop] Loop exhausted after ${MAX_LOOP_ITERATIONS} iterations; falling back to stub`,
  )
  await safeApplyDecision(kernel, { _tag: "Finish", reason: "loop exhausted" }, logger)
  return {
    reply: stubReply(args.content, args.fromUserId, args.projectId),
    iterations: MAX_LOOP_ITERATIONS,
    toolCalls,
    finalDecision: lastDecision,
    traces: [...traces, `loop exhausted (max=${MAX_LOOP_ITERATIONS})`],
  }
}

/**
 * Apply a decision via the kernel, logging + swallowing the
 * "already completed" error. Lets the butler loop tolerate replay
 * attempts on a finished kernel without throwing.
 */
async function safeApplyDecision(
  kernel: AgentKernel,
  decision: ModelDecision,
  logger: ButlerLoopLogger,
): Promise<void> {
  try {
    await kernel.applyDecision(decision)
  } catch (err) {
    logger.warn(
      `[v5-butler-loop] applyDecision(${decision._tag}) failed; continuing:`,
      err instanceof Error ? err.message : String(err),
    )
  }
}

/**
 * Compact a tool output string for the operator trace log. Long
 * outputs are truncated so the trace stays scannable.
 */
function summarizeForLog(s: string, maxLen = 80): string {
  if (s.length <= maxLen) return s
  return `${s.slice(0, maxLen - 3)}...`
}
