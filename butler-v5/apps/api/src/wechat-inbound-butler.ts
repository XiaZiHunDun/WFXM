import { Effect } from "effect"
import type { EventBridge } from "@butler/runtime/bridge.js"
import type { Wiring } from "./wiring.js"
import { findTool, makeWeibutlerTools, runTool, type ToolDefinition } from "./tools.js"
import { pickLLMProvider, type LLMAdapter, type LLMMessage } from "@butler/adapters"
import { buildWechatInboundMessages, stubReply } from "./wechat-inbound-llm.js"
import { AgentKernel, decodeDecision, type ModelDecision } from "./wechat-kernel.js"

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
 * The loop:
 *  1. Open a turn on a fresh AgentKernel (records TurnOpened).
 *  2. Build messages (system + recent history + current user msg).
 *  3. Call the LLM with the wechat tool set.
 *  4. Decode the model decision (Respond / CallTool / Finish / ...).
 *  5. Apply the decision via the kernel; for CallTool, execute the
 *     tool and feed the result back into the messages array, then
 *     loop to step 3.
 *  6. Bound by MAX_LOOP_ITERATIONS; on overrun, fall back to the stub
 *     reply (the v4 contract is preserved).
 */
export async function runButlerLoop(args: {
  readonly wiring: Wiring
  readonly conversationId: string
  readonly content: string
  readonly fromUserId: string
  readonly projectId: string
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

  // 2. Build the initial messages array (system + user). Recent
  //    history is fetched once at the start; tool-call additions
  //    accumulate in `trajectoryMessages` for subsequent iterations.
  const messages: LLMMessage[] = buildWechatInboundMessages(args.content).map((m) => ({
    role: m.role,
    content: m.content,
  }))

  const tools: readonly ToolDefinition[] = makeWeibutlerTools({
    bridge,
    conversationId: args.conversationId,
  })

  const adapter = args.adapter ?? pickLLMProvider(env)
  if (!adapter) {
    // No LLM configured — apply a Finish decision so the kernel
    // transitions to 'completed' and we return the stub reply. The
    // v4 contract is preserved.
    await safeApplyDecision(kernel, { _tag: "Finish", reason: "no LLM configured" }, logger)
    return {
      reply: stubReply(args.content, args.fromUserId, args.projectId),
      iterations: 0,
      toolCalls: 0,
      finalDecision: "Finish",
      traces: ["no LLM configured; returned stub"],
    }
  }

  const traces: string[] = []
  let toolCalls = 0
  let lastDecision: ModelDecision["_tag"] = "Finish"

  // 3. Main loop.
  for (let iteration = 0; iteration < MAX_LOOP_ITERATIONS; iteration++) {
    // R8.x.3 dispatches tool execution entirely through decodeDecision
    // (the model returns a JSON CallTool decision). We deliberately do
    // NOT pass tools to the adapter — passing them triggers OpenAI-style
    // tool_calls in the response, which we don't parse here. Future
    // R8.x.4 work can wire real tool_calls by extending LLMMessage and
    // the loop. Tool set is advertised via the system prompt instead.
    const outcome = await Effect.runPromise(
      adapter.complete(messages).pipe(
        Effect.match({
          onFailure: (err) => {
            logger.error(
              `[v5-butler-loop] LLM call failed (fromUserId=${args.fromUserId}); falling back to stub:`,
              err,
            )
            return { ok: false as const, reason: err instanceof Error ? err.message : String(err) }
          },
          onSuccess: (msg) => ({ ok: true as const, message: msg }),
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

    const raw = outcome.message.content.trim()
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
        // No child agent dispatch wired yet (R8.x.4 will land
        // delegate-runtime). Treat as Finish for now so the loop
        // terminates.
        logger.warn(
          `[v5-butler-loop] Delegate decision not yet supported; treating as Finish (iteration ${iteration})`,
        )
        await safeApplyDecision(
          kernel,
          { _tag: "Finish", reason: "delegate not supported" },
          logger,
        )
        return {
          reply: stubReply(args.content, args.fromUserId, args.projectId),
          iterations: iteration + 1,
          toolCalls,
          finalDecision: "Delegate",
          traces: [...traces, `delegate unsupported (role=${decision.role})`],
        }
      }
      case "CallTool": {
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
        const toolResult = await runTool(def, decision.args, { timeoutMs: TOOL_TIMEOUT_MS })
        const trace: ToolTrace = {
          iteration,
          toolName: decision.toolName,
          ok: toolResult.ok,
          summary: toolResult.ok
            ? summarizeForLog(String(toolResult.output))
            : `error: ${toolResult.reason}`,
        }
        traces.push(`${trace.toolName}@${trace.iteration}: ${trace.summary}`)
        // Feed the tool result back as a "tool" role message so the
        // model can use it on the next iteration.
        const toolMessage: LLMMessage = {
          role: "user",
          content: toolResult.ok
            ? `[tool:${trace.toolName}] ${String(toolResult.output)}`
            : `[tool:${trace.toolName}] ERROR: ${toolResult.reason}`,
        }
        messages.push(toolMessage)
        // Continue the loop — model will see the tool result and decide
        // whether to call another tool or respond.
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
