/**
 * Conversation Loop — Execution-side multi-turn model/tool cycle (A7).
 *
 * Owns AgentKernel decision application + iteration bound. Delivery shells
 * (apps/api) inject LLM / tools / stub reply via ports; no WeChat/Wiring
 * imports here.
 */
import type { AgentKernel } from "../agent-kernel.js"
import { decodeDecision, type ModelDecision } from "../decision.js"
import { RunPauseForApproval } from "../run-engine.js"
import type { RunResult, ToolDefinition } from "../tool-runtime.js"
import { redactSecretText, shouldRedactToolResults } from "../secret-redact.js"

/** Tool output as model-visible text; redacted in strict mode (default off). */
function formatToolOutput(output: unknown): string {
  const text = typeof output === "string" ? output : JSON.stringify(output)
  return shouldRedactToolResults(process.env) ? redactSecretText(text) : text
}

export const DEFAULT_MAX_LOOP_ITERATIONS = 5

/**
 * Phase D eval fix B-06: stuck-loop detection. If the LLM invokes the
 * same capability with the same args `>= STUCK_LOOP_THRESHOLD` times within
 * one loop run, short-circuit with a Finish + descriptive trace instead
 * of letting the loop exhaust the iteration cap with a silent stub.
 *
 * Tunable via BUTLER_V5_STUCK_LOOP_THRESHOLD env. Default 3 — one legit
 * retry (transient tool failure) does not trip the detector.
 */
export const DEFAULT_STUCK_LOOP_THRESHOLD = 3

function resolveStuckLoopThreshold(env: NodeJS.ProcessEnv = process.env): number {
  const raw = (env["BUTLER_V5_STUCK_LOOP_THRESHOLD"] ?? "").trim()
  if (!raw) return DEFAULT_STUCK_LOOP_THRESHOLD
  const parsed = Number(raw)
  return Number.isFinite(parsed) && parsed >= 1 ? Math.floor(parsed) : DEFAULT_STUCK_LOOP_THRESHOLD
}

/**
 * Phase D fix B-08/10: decoder feedback retry. When `decodeDecision`
 * returns ok=false with a "structured" failure (parseable JSON but
 * wrong shape — e.g. unknown tag, missing field), push a user-message
 * into the LLM context and let the loop iterate once more so the LLM
 * can self-correct. Plain-text replies (reason: "invalid JSON") and
 * non-object payloads fall through without retry to preserve the
 * original "plain text → Respond" behavior expected by the bulk of
 * the existing test suite.
 *
 * Tunable via BUTLER_V5_MAX_DECODE_RETRIES env. Default 1.
 */
export const DEFAULT_MAX_DECODE_RETRIES = 1

function resolveMaxDecodeRetries(env: NodeJS.ProcessEnv = process.env): number {
  const raw = (env["BUTLER_V5_MAX_DECODE_RETRIES"] ?? "").trim()
  if (!raw) return DEFAULT_MAX_DECODE_RETRIES
  const parsed = Number(raw)
  return Number.isFinite(parsed) && parsed >= 0 ? Math.floor(parsed) : DEFAULT_MAX_DECODE_RETRIES
}

/**
 * Per-LLM-call timeout (Phase D eval fix B-09). Each iteration's LLM
 * completion is bounded; a slow / hung provider returns a synthetic
 * `{ ok: false, reason: "LLM timeout after Xms" }` so the loop falls
 * through to the existing "llm failure" Finish + stub reply path
 * instead of stalling the owner indefinitely.
 *
 * Tunable via BUTLER_V5_LLM_TIMEOUT_MS env. Default 30s is generous
 * for DeepSeek-Flash / Sonnet production but bounds worst-case at
 * 5 × 30s = 2.5 min per loop max.
 */
export const DEFAULT_LLM_TIMEOUT_MS = 30_000

function resolveLLMTimeoutMs(env: NodeJS.ProcessEnv = process.env): number {
  const raw = (env["BUTLER_V5_LLM_TIMEOUT_MS"] ?? "").trim()
  if (!raw) return DEFAULT_LLM_TIMEOUT_MS
  const parsed = Number(raw)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_LLM_TIMEOUT_MS
}

export interface ConversationLoopLogger {
  readonly warn: (message: string, extra?: unknown) => void
  readonly error: (message: string, error: unknown) => void
}

export interface ConversationLoopToolCall {
  readonly id: string
  readonly name: string
  readonly args: Readonly<Record<string, unknown>>
}

export interface ConversationLoopMessage {
  readonly role: "system" | "user" | "assistant" | "tool"
  readonly content: string
  readonly toolCalls?: readonly ConversationLoopToolCall[]
  readonly toolCallId?: string
  readonly toolName?: string
}

export interface ConversationLoopLlmTool {
  readonly name: string
  readonly description?: string
  readonly parameters?: unknown
}

export interface ConversationLoopResult {
  readonly reply: string
  readonly iterations: number
  readonly toolCalls: number
  readonly finalDecision: ModelDecision["_tag"]
  readonly traces: readonly string[]
}

/** Hash a (capabilityName, args) pair for stuck-loop detection. */
function capSignature(name: string, args: Readonly<Record<string, unknown>>): string {
  return `${name}:${JSON.stringify(args)}`
}

export interface ConversationLoopPorts {
  readonly complete: (
    messages: readonly ConversationLoopMessage[],
    tools: readonly ConversationLoopLlmTool[],
  ) => Promise<
    | {
        readonly ok: true
        readonly response: {
          readonly content: string
          readonly toolCalls: readonly ConversationLoopToolCall[]
          /**
           * D23: optional provider-agnostic token usage. When the
           * adapter surfaces `usage` it propagates here so the loop
           * can attach it to the trace event emitted for the LLM
           * call. Stays `undefined` for adapters / fixtures that do
           * not report usage.
           */
          readonly usage?: {
            readonly inputTokens: number
            readonly outputTokens: number
            readonly totalTokens: number
          }
        }
      }
    | { readonly ok: false; readonly reason: string }
  >
  readonly findTool: (name: string) => ToolDefinition | undefined
  /**
   * Execute a tool. May throw `RunPauseForApproval` when Policy requests
   * Owner confirmation (delivery shell encodes the pause payload).
   */
  readonly executeTool: (
    def: ToolDefinition,
    args: Readonly<Record<string, unknown>>,
  ) => Promise<RunResult>
  readonly stubReply: () => string
  readonly persistAssistantReply?: (content: string) => Promise<void>
  readonly logger?: ConversationLoopLogger
}

const defaultLogger: ConversationLoopLogger = {
  warn: (message, extra) => {
    // eslint-disable-next-line no-console -- intentional stderr log for operator debugging
    console.warn(message, extra ?? "")
  },
  error: (message, error) => {
    // eslint-disable-next-line no-console -- intentional stderr log for operator debugging
    console.error(message, error)
  },
}

async function safeApplyDecision(
  kernel: AgentKernel,
  decision: ModelDecision,
  logger: ConversationLoopLogger,
): Promise<void> {
  try {
    await kernel.applyDecision(decision)
  } catch (err) {
    logger.warn(
      `[conversation-loop] applyDecision(${decision._tag}) failed; continuing:`,
      err instanceof Error ? err.message : String(err),
    )
  }
}

/**
 * Race a ports.complete call against a timer; returns either the LLM
 * response or a `{ ok: false, reason: "LLM timeout after Nms" }` synthetic
 * failure. Cancels the pending timer when the LLM resolves first (no
 * leaked setTimeout) to keep the loop GC-clean.
 */
async function completeWithTimeout(
  invoke: () => ReturnType<ConversationLoopPorts["complete"]>,
  timeoutMs: number,
): Promise<Awaited<ReturnType<ConversationLoopPorts["complete"]>> | { readonly ok: false; readonly reason: string }> {
  let timer: NodeJS.Timeout | undefined
  const timeoutPromise = new Promise<{ readonly ok: false; readonly reason: string }>(
    (resolve) => {
      timer = setTimeout(
        () => resolve({ ok: false, reason: `LLM timeout after ${timeoutMs}ms` }),
        timeoutMs,
      )
    },
  )
  try {
    return await Promise.race([invoke(), timeoutPromise])
  } finally {
    if (timer) clearTimeout(timer)
  }
}

function summarizeForLog(s: string, maxLen = 80): string {
  if (s.length <= maxLen) return s
  return `${s.slice(0, maxLen - 3)}...`
}

async function executeToolInLoop(args: {
  readonly ports: ConversationLoopPorts
  readonly def: ToolDefinition
  readonly toolArgs: Readonly<Record<string, unknown>>
  readonly iteration: number
  readonly toolCalls: number
  readonly traces: readonly string[]
  readonly toolName: string
}): Promise<RunResult> {
  try {
    return await args.ports.executeTool(args.def, args.toolArgs)
  } catch (err) {
    if (!(err instanceof RunPauseForApproval)) throw err
    const base =
      err.payload && typeof err.payload === "object"
        ? (err.payload as Partial<ConversationLoopResult>)
        : {}
    throw new RunPauseForApproval({
      reply: typeof base.reply === "string" ? base.reply : "需要审批后才能继续。",
      iterations: args.iteration + 1,
      toolCalls: args.toolCalls,
      finalDecision: base.finalDecision ?? "WaitForApproval",
      traces: [
        ...args.traces,
        ...(Array.isArray(base.traces) ? base.traces : []),
        `${args.toolName}@${args.iteration}: waiting approval`,
      ],
    } satisfies ConversationLoopResult)
  }
}

/**
 * Run the multi-turn conversation loop after the turn is opened and
 * initial messages are prepared by the delivery shell.
 */
export async function runConversationLoop(input: {
  readonly kernel: AgentKernel
  readonly messages: ConversationLoopMessage[]
  readonly llmTools: readonly ConversationLoopLlmTool[]
  readonly ports: ConversationLoopPorts
  readonly maxIterations?: number
  readonly initialTraces?: readonly string[]
  /** Per-LLM-call timeout in ms (default: `DEFAULT_LLM_TIMEOUT_MS` = 30_000). */
  readonly llmTimeoutMs?: number
  /** Stuck-loop threshold (Phase D fix B-06). Default reads
   *  BUTLER_V5_STUCK_LOOP_THRESHOLD from env (else 3). */
  readonly stuckLoopThreshold?: number
  /** Max decoder-failure retries before fallback (Phase D fix B-08/10).
   *  Default reads BUTLER_V5_MAX_DECODE_RETRIES from env (else 1). */
  readonly maxDecodeRetries?: number
}): Promise<ConversationLoopResult> {
  const logger = input.ports.logger ?? defaultLogger
  const maxIterations = input.maxIterations ?? DEFAULT_MAX_LOOP_ITERATIONS
  const llmTimeoutMs = input.llmTimeoutMs ?? resolveLLMTimeoutMs()
  const stuckLoopThreshold = input.stuckLoopThreshold ?? resolveStuckLoopThreshold()
  const maxDecodeRetries = input.maxDecodeRetries ?? resolveMaxDecodeRetries()
  const messages = [...input.messages]
  const traces: string[] = [...(input.initialTraces ?? [])]
  let toolCalls = 0
  const callSignatures = new Map<string, number>()
  let decodeFailuresThisLoop = 0
  let firstDecodeFailureReason = ""
  let lastNonEmptyRaw = ""

  for (let iteration = 0; iteration < maxIterations; iteration++) {
    const outcome = await completeWithTimeout(
      () => input.ports.complete(messages, input.llmTools),
      llmTimeoutMs,
    )

    if (!outcome.ok) {
      await safeApplyDecision(
        input.kernel,
        { _tag: "Finish", reason: `llm failure: ${outcome.reason}` },
        logger,
      )
      return {
        reply: input.ports.stubReply(),
        iterations: iteration + 1,
        toolCalls,
        finalDecision: "Finish",
        traces: [...traces, `llm failure: ${outcome.reason}`],
      }
    }

    const response = outcome.response

    if (response.toolCalls.length > 0) {
      messages.push({
        role: "assistant",
        content: response.content,
        toolCalls: response.toolCalls,
      })

      const toolResultMessages: ConversationLoopMessage[] = []
      for (const tc of response.toolCalls) {
        const def = input.ports.findTool(tc.name)
        if (!def) {
          logger.warn(
            `[conversation-loop] Unknown tool '${tc.name}' at iteration ${iteration}; pushing error result`,
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
        // Phase D fix B-06: stuck-loop detection. Same (name, args) signature
        // hits `stuckLoopThreshold` times — short-circuit with descriptive trace.
        const sig = capSignature(tc.name, tc.args as Readonly<Record<string, unknown>>)
        const sigCount = (callSignatures.get(sig) ?? 0) + 1
        callSignatures.set(sig, sigCount)
        if (sigCount >= stuckLoopThreshold) {
          const reason = `stuck-loop: ${tc.name} invoked ${sigCount}x with same args; aborting`
          logger.warn(`[conversation-loop] ${reason}`)
          await safeApplyDecision(
            input.kernel,
            { _tag: "Finish", reason: `stuck-loop: ${tc.name}` },
            logger,
          )
          return {
            reply: input.ports.stubReply(),
            iterations: iteration + 1,
            toolCalls,
            finalDecision: "Finish",
            traces: [...traces, reason],
          }
        }
        toolCalls += 1
        const toolResult = await executeToolInLoop({
          ports: input.ports,
          def,
          toolArgs: tc.args,
          iteration,
          toolCalls,
          traces,
          toolName: tc.name,
        })
        traces.push(
          `${tc.name}@${iteration}: ${
            toolResult.ok
              ? summarizeForLog(String(toolResult.output))
              : `error: ${toolResult.reason}`
          }`,
        )
        toolResultMessages.push({
          role: "tool",
          content: toolResult.ok ? formatToolOutput(toolResult.output) : `[error] ${toolResult.reason}`,
          toolCallId: tc.id,
          toolName: tc.name,
        })
      }
      messages.push(...toolResultMessages)
      continue
    }

    const raw = response.content.trim()
    if (raw) lastNonEmptyRaw = raw
    const decoded = decodeDecision(raw)
    if (!decoded.ok) {
      const preview = raw.length > 120 ? `${raw.slice(0, 120)}…` : raw
      logger.warn(
        `[conversation-loop] decodeDecision failed at iteration ${iteration}: ${decoded.reason}; raw=${JSON.stringify(preview)}`,
      )
      if (!firstDecodeFailureReason) firstDecodeFailureReason = decoded.reason
      decodeFailuresThisLoop += 1
      // B-08/10: only retry when the LLM emitted something structured (parseable
      // JSON but wrong shape). Plain-text replies (reason "invalid JSON") and
      // non-object payloads fall through without retry — preserves "plain text →
      // Respond" path tested by most existing tests.
      const isStructuredFailure = decoded.reason !== "invalid JSON"
      if (isStructuredFailure && decodeFailuresThisLoop <= maxDecodeRetries) {
        // Phase D fix B-08/10: push structured feedback so the LLM gets one
        // self-correction cycle. main `traces` records the retry attempt;
        // OWNER still sees nothing until either decode succeeds or we hit the cap.
        messages.push({
          role: "user",
          content: `[system] decision-decode-fail: ${decoded.reason}. If a Decision was intended, retry with valid JSON. Raw reply was: \`\`\`${raw.slice(0, 200)}\`\`\``,
        })
        traces.push(
          `decode failed retry ${decodeFailuresThisLoop}/${maxDecodeRetries}: ${decoded.reason}`,
        )
        continue
      }
      // Max retries exceeded (Phase D fix B-08/10): prefer the last non-empty
      // LLM content (legitimate plain-text response); fall back to stub reply
      // when ALL attempts were empty (matches pre-fix behavior for empty raw).
      const respondContent = raw || lastNonEmptyRaw || input.ports.stubReply()
      const respondDecision: ModelDecision = {
        _tag: "Respond",
        content: respondContent,
      }
      await safeApplyDecision(input.kernel, respondDecision, logger)
      return {
        reply: respondContent,
        iterations: iteration + 1,
        toolCalls,
        finalDecision: "Respond",
        traces: [
          ...traces,
          `decode failed (${decoded.reason}); max retries (${maxDecodeRetries}) exceeded`,
        ],
      }
    }

    const decision = decoded.value

    switch (decision._tag) {
      case "Respond": {
        await safeApplyDecision(input.kernel, decision, logger)
        const text = decision.content.trim()
        const reply = text || input.ports.stubReply()
        if (input.ports.persistAssistantReply) {
          await input.ports.persistAssistantReply(reply)
        }
        return {
          reply,
          iterations: iteration + 1,
          toolCalls,
          finalDecision: "Respond",
          traces,
        }
      }
      case "Finish": {
        await safeApplyDecision(input.kernel, decision, logger)
        return {
          reply: input.ports.stubReply(),
          iterations: iteration + 1,
          toolCalls,
          finalDecision: "Finish",
          traces,
        }
      }
      case "WaitForApproval": {
        await safeApplyDecision(input.kernel, decision, logger)
        return {
          reply: `[需要确认] ${decision.question}`,
          iterations: iteration + 1,
          toolCalls,
          finalDecision: "WaitForApproval",
          traces: [...traces, `WaitForApproval echoed: ${decision.question}`],
        }
      }
      case "StartChildRun": {
        await safeApplyDecision(input.kernel, decision, logger)
        const def = input.ports.findTool("delegate_to_subagent")
        if (!def) {
          logger.warn(
            `[conversation-loop] delegate_to_subagent tool not registered; treating as Finish`,
          )
          traces.push("delegate_to_subagent missing")
          await safeApplyDecision(
            input.kernel,
            { _tag: "Finish", reason: "delegate_to_subagent missing" },
            logger,
          )
          return {
            reply: input.ports.stubReply(),
            iterations: iteration + 1,
            toolCalls,
            finalDecision: "StartChildRun",
            traces,
          }
        }
        toolCalls += 1
        const toolResult = await executeToolInLoop({
          ports: input.ports,
          def,
          toolArgs: { task: decision.objective, role: decision.role },
          iteration,
          toolCalls,
          traces,
          toolName: "delegate_to_subagent",
        })
        traces.push(
          `delegate_to_subagent@${iteration}: ${
            toolResult.ok
              ? summarizeForLog(String(toolResult.output))
              : `error: ${toolResult.reason}`
          }`,
        )
        const toolCallId = `json-${iteration}-delegate_to_subagent`
        messages.push({
          role: "assistant",
          content: JSON.stringify(decision),
          toolCalls: [
            {
              id: toolCallId,
              name: "delegate_to_subagent",
              args: { task: decision.objective, role: decision.role },
            },
          ],
        })
        messages.push({
          role: "tool",
          content: toolResult.ok ? formatToolOutput(toolResult.output) : `[error] ${toolResult.reason}`,
          toolCallId,
          toolName: "delegate_to_subagent",
        })
        continue
      }
      case "CallCapability": {
        await safeApplyDecision(input.kernel, decision, logger)
        const def = input.ports.findTool(decision.name)
        if (!def) {
          logger.warn(
            `[conversation-loop] Unknown tool '${decision.name}' at iteration ${iteration}; treating as Finish`,
          )
          traces.push(`unknown tool: ${decision.name}`)
          return {
            reply: input.ports.stubReply(),
            iterations: iteration + 1,
            toolCalls,
            finalDecision: "CallCapability",
            traces,
          }
        }
        toolCalls += 1
        const toolResult = await executeToolInLoop({
          ports: input.ports,
          def,
          toolArgs: decision.arguments,
          iteration,
          toolCalls,
          traces,
          toolName: decision.name,
        })
        traces.push(
          `${decision.name}@${iteration}: ${
            toolResult.ok
              ? summarizeForLog(String(toolResult.output))
              : `error: ${toolResult.reason}`
          }`,
        )
        messages.push({
          role: "assistant",
          content: JSON.stringify(decision),
          toolCalls: [
            {
              id: decision.callId ?? `json-${iteration}-${decision.name}`,
              name: decision.name,
              args: { ...decision.arguments },
            },
          ],
        })
        messages.push({
          role: "tool",
          content: toolResult.ok ? formatToolOutput(toolResult.output) : `[error] ${toolResult.reason}`,
          toolCallId: decision.callId ?? `json-${iteration}-${decision.name}`,
          toolName: decision.name,
        })
        continue
      }
      default: {
        const _: never = decision
        void _
        return {
          reply: input.ports.stubReply(),
          iterations: iteration + 1,
          toolCalls,
          finalDecision: "Finish",
          traces,
        }
      }
    }
  }

  logger.warn(
    `[conversation-loop] Loop exhausted after ${maxIterations} iterations; falling back to clarification`,
  )
  await safeApplyDecision(input.kernel, { _tag: "Finish", reason: "loop exhausted" }, logger)
  return {
    reply: `[需要澄清] 模型未在 ${maxIterations} 轮内收敛，请补充信息或缩小范围。`,
    iterations: maxIterations,
    toolCalls,
    finalDecision: "Finish",
    traces: [...traces, `loop exhausted (max=${maxIterations})`],
  }
}
