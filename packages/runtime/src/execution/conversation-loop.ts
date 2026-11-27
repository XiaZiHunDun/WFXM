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
 * 工具预算要兑现，轮次必须够：每轮至少能执行一次工具调用，还要留 1 轮
 * 给最终答复。调用方显式给的 maxIterations 作为下限保留，只在预算更大时
 * 抬升轮次上限；否则 `maxToolCalls=8` 会被 5 轮迭代卡死。
 */
export function resolveLoopIterations(
  requested: number | undefined,
  maxToolCalls: number | undefined,
): number {
  const base = requested ?? DEFAULT_MAX_LOOP_ITERATIONS
  if (typeof maxToolCalls !== "number") return base
  return Math.max(base, maxToolCalls + 1)
}

/**
 * 最后一轮必须收敛为答复：不再暴露工具，并显式要求 Respond。
 * 否则模型会把所有轮次花在工具调用上，用户最终只收到兜底话术。
 */
const FINAL_ITERATION_NUDGE =
  "这是最后一轮：不要调用任何工具。请直接给用户一个有用答复（Respond）；信息不足时用 Respond 提 1 个具体澄清问题，不要 Finish。"

/**
 * 工具预算提示：模型看不到 Run 的 budget，容易用 pwd/ls/find 反复探索把额度耗尽。
 * 每轮把剩余额度放在消息末尾，接近上限时明确要求收敛。
 */
function toolBudgetNote(maxToolCalls: number, used: number): string {
  const remaining = Math.max(0, maxToolCalls - used)
  const head = `工具预算：本 Run 最多 ${maxToolCalls} 次工具调用，已用 ${used} 次，剩余 ${remaining} 次。`
  if (remaining === 0) {
    return `${head}额度已用完：不要再调用工具，请直接基于已有信息给出答复或向用户澄清。`
  }
  if (remaining <= 2) {
    return `${head}剩余额度足以完成目标动作：不要再做探索性调用（pwd/ls/find/grep），请直接执行用户要求的关键动作（write_file / 删除 / 运行测试等），完成后再给出结论，不要只给建议。`
  }
  return `${head}避免重复或探索性调用，直接完成用户要求的目标动作（必要时调用工具），再给出结论。`
}

/** Phase 7 fix F36: 委派声明守卫的提示文案（纯文本与 Respond 两条路径共用）。 */
const DELEGATION_CLAIM_NUDGE =
  "[system] 你回复里声称已经委派，但本轮没有成功派发子任务，子代理并未真正启动。如果确实需要子代理，请立刻调用 delegate_to_subagent（goal 里写完整任务与验证要求）；如果不需要，请直接给出最终答复，不要声称已派发。"

/**
 * Phase 7 fix F36: 判断一段回复是否在声称「已派子代理」。
 *
 * F11 只匹配「已派/已交给/已委派/派给/交给」，实测漏掉了
 * 「已在后台让 developer 动手」这类说法，导致 0 工具调用也被当作完成。
 * 这里补上「让 … 动手/开工/执行/处理/去做」「安排 … 动手」等变体。
 */
function looksLikeDelegationClaim(text: string): boolean {
  const raw = text ?? ""
  if (!/(子代理|执行代理|developer|后台)/iu.test(raw)) return false
  return /(已派|已交给|已委派|派给|交给|让[^\n。]{0,24}(?:动手|开工|执行|处理|去做)|安排[^\n。]{0,12}(?:动手|开工|执行))/u.test(
    raw,
  )
}

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
 * 空内容重试：provider 偶发返回空 content 且没有 tool call（推理 token
 * 耗尽、上游截断等），若直接 decode 只会落到 stub 回复（"已收到，正在
 * 处理中。"）。这里给模型一次明确的"必须输出决策"提示后重试。
 * Tunable via BUTLER_V5_MAX_EMPTY_CONTENT_RETRIES env. Default 1.
 */
export const DEFAULT_MAX_EMPTY_CONTENT_RETRIES = 1

function resolveMaxEmptyContentRetries(env: NodeJS.ProcessEnv = process.env): number {
  const raw = (env["BUTLER_V5_MAX_EMPTY_CONTENT_RETRIES"] ?? "").trim()
  if (!raw) return DEFAULT_MAX_EMPTY_CONTENT_RETRIES
  const parsed = Number(raw)
  return Number.isFinite(parsed) && parsed >= 0
    ? Math.floor(parsed)
    : DEFAULT_MAX_EMPTY_CONTENT_RETRIES
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
// D74 T2 (audit #20 CQ-006): local constant — kept in sync with
// @butler/adapters DEFAULT_LLM_TIMEOUT_MS (packages/adapters/src/defaults.ts).
// Runtime doesn't depend on adapters (would create dep cycle via ports/domain),
// so the value is duplicated here and an integration test asserts equality.
// Drift would surface as a 2-line architecture-decision-record change.
const DEFAULT_LLM_TIMEOUT_MS = 30_000

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

// D60 T3.1 (audit #2 F-05): structurally equivalent to `LLMToolCall`
// (same id/name/args fields). Args was previously typed
// `Readonly<Record<string, unknown>>` which blocked the structural
// assignment from `LLMMMessage[]` in subagent-worker; widened to
// `Record<string, unknown>` so LLMToolCall is directly assignable
// without an `as unknown as` cast.
export interface ConversationLoopToolCall {
  readonly id: string
  readonly name: string
  readonly args: Record<string, unknown>
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
  // D61 T3 (audit #2 F-01/02/03 widening): match the required fields of
  // `LLMTool` so a `readonly ConversationLoopLlmTool[]` is directly
  // assignable to `readonly LLMTool[]` (no `as unknown as` cast needed).
  // All callers pass `LLMTool[]` from `llmToolsForCapabilities`, which
  // already has both fields — the previous optional form was a holdover
  // from when conversation-loop accepted arbitrary tool shapes.
  readonly description: string
  readonly parameters: {
    readonly type: "object"
    readonly properties?: Record<string, unknown>
    readonly required?: readonly string[]
  }
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

/**
 * Phase 7 fix F7: suggest the closest advertised tool name for an unknown
 * one. Models frequently guess plausible-but-wrong names (`list_files` vs
 * `list_dir`); a short "did you mean" hint prevents burning iterations.
 * Returns `undefined` when nothing is close enough.
 */
function suggestToolName(name: string, available: readonly string[]): string | undefined {
  if (available.length === 0) return undefined
  const lower = name.toLowerCase()
  let best: string | undefined
  let bestDistance = Number.POSITIVE_INFINITY
  for (const candidate of available) {
    const distance = editDistance(lower, candidate.toLowerCase())
    if (distance < bestDistance) {
      bestDistance = distance
      best = candidate
    }
  }
  const tolerance = Math.max(2, Math.floor(name.length * 0.6))
  return bestDistance <= tolerance ? best : undefined
}

/** Levenshtein distance (iterative single-row implementation). */
function editDistance(a: string, b: string): number {
  if (a === b) return 0
  if (a.length === 0) return b.length
  if (b.length === 0) return a.length
  let previous = Array.from({ length: b.length + 1 }, (_, i) => i)
  for (let i = 1; i <= a.length; i += 1) {
    const current = [i]
    for (let j = 1; j <= b.length; j += 1) {
      const substitution = (previous[j - 1] ?? 0) + (a[i - 1] === b[j - 1] ? 0 : 1)
      const insertion = (current[j - 1] ?? 0) + 1
      const deletion = (previous[j] ?? 0) + 1
      current[j] = Math.min(substitution, insertion, deletion)
    }
    previous = current
  }
  return previous[b.length] ?? Math.max(a.length, b.length)
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
): Promise<
  | Awaited<ReturnType<ConversationLoopPorts["complete"]>>
  | { readonly ok: false; readonly reason: string }
> {
  let timer: NodeJS.Timeout | undefined
  const timeoutPromise = new Promise<{ readonly ok: false; readonly reason: string }>((resolve) => {
    timer = setTimeout(
      () => resolve({ ok: false, reason: `LLM timeout after ${timeoutMs}ms` }),
      timeoutMs,
    )
  })
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

export interface ConversationLoopInput {
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
  /** Empty-content retries before the stub fallback. Default reads
   *  BUTLER_V5_MAX_EMPTY_CONTENT_RETRIES from env (else 1). */
  readonly maxEmptyContentRetries?: number
  /** Tool-call budget for this run; also raises the iteration cap. */
  readonly maxToolCalls?: number
  /**
   * Phase 7 fix F2b: when true, a plain-text reply before the final turn is
   * treated as unfinished work — the loop nudges the model to keep calling
   * tools instead of ending. Used by subagent loops that must land files.
   */
  readonly toolFirst?: boolean
  /**
   * Phase 7 fix F11: the main butler sometimes answers with prose like
   * "已派子代理处理，结果一到就转给你" without ever calling
   * `delegate_to_subagent`, so nothing actually starts. When enabled, a
   * non-final prose reply that claims a delegation triggers one corrective
   * nudge instead of being accepted as the final answer.
   */
  readonly delegationClaimGuard?: boolean
  /**
   * Phase 7 fix F27 (hard cap): maximum subagent delegations per loop run
   * (i.e. per owner turn). Undefined means unlimited (legacy behavior).
   * Beyond the cap the loop refuses further `StartChildRun` decisions and
   * tells the model to report progress and finish instead of fanning out.
   */
  readonly maxDelegationsPerTurn?: number
}

/**
 * Loop engine selector. `pi` routes the same input through the vendored pi
 * agent loop; anything else keeps the native loop. The default stays native
 * until the capability suite confirms parity.
 */
export function selectLoopEngine(env: NodeJS.ProcessEnv = process.env): "native" | "pi" {
  return (env["BUTLER_V5_LOOP_ENGINE"] ?? "").trim().toLowerCase() === "pi" ? "pi" : "native"
}

/**
 * Run the multi-turn conversation loop after the turn is opened and
 * initial messages are prepared by the delivery shell.
 */
export async function runConversationLoop(
  input: ConversationLoopInput,
): Promise<ConversationLoopResult> {
  if (selectLoopEngine() === "pi") {
    // Lazy import keeps the vendored pi source out of the native hot path.
    const { runPiConversationLoop } = await import("./pi-engine.js")
    return runPiConversationLoop(input)
  }
  return runNativeConversationLoop(input)
}

async function runNativeConversationLoop(
  input: ConversationLoopInput,
): Promise<ConversationLoopResult> {
  const logger = input.ports.logger ?? defaultLogger
  const maxIterations = resolveLoopIterations(input.maxIterations, input.maxToolCalls)
  const llmTimeoutMs = input.llmTimeoutMs ?? resolveLLMTimeoutMs()
  const stuckLoopThreshold = input.stuckLoopThreshold ?? resolveStuckLoopThreshold()
  const maxDecodeRetries = input.maxDecodeRetries ?? resolveMaxDecodeRetries()
  const maxEmptyContentRetries = input.maxEmptyContentRetries ?? resolveMaxEmptyContentRetries()
  const messages = [...input.messages]
  const traces: string[] = [...(input.initialTraces ?? [])]
  let toolCalls = 0
  const callSignatures = new Map<string, number>()
  let decodeFailuresThisLoop = 0
  let emptyContentRetries = 0
  let firstDecodeFailureReason = ""
  let lastNonEmptyRaw = ""
  let budgetNoteIndex = -1
  let budgetExhaustedNotified = false
  let toolFirstNudges = 0
  const maxToolFirstNudges = 2
  let delegationClaimNudges = 0
  // F27 hard cap: successful delegations started by this loop run.
  let delegations = 0

  for (let iteration = 0; iteration < maxIterations; iteration++) {
    const isFinalIteration = iteration === maxIterations - 1
    const toolsExhausted = typeof input.maxToolCalls === "number" && toolCalls >= input.maxToolCalls
    if (typeof input.maxToolCalls === "number" && input.maxToolCalls >= 0) {
      // 保持预算提示在消息末尾（最新），避免被后续工具结果淹没。
      if (budgetNoteIndex >= 0) messages.splice(budgetNoteIndex, 1)
      messages.push({
        role: "system",
        content: toolBudgetNote(input.maxToolCalls, toolCalls),
      })
      budgetNoteIndex = messages.length - 1
    }
    // 硬约束：额度用尽后不再暴露工具，只允许给出答复/澄清。
    if (toolsExhausted && !budgetExhaustedNotified) {
      budgetExhaustedNotified = true
      messages.push({
        role: "system",
        content: `工具调用额度已用尽（上限 ${input.maxToolCalls} 次）：不要再调用任何工具，请直接基于已有信息给出答复或向用户澄清。`,
      })
    }
    if (isFinalIteration && input.llmTools.length > 0) {
      messages.push({ role: "system", content: FINAL_ITERATION_NUDGE })
    }
    const outcome = await completeWithTimeout(
      () =>
        input.ports.complete(messages, isFinalIteration || toolsExhausted ? [] : input.llmTools),
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
        if (typeof input.maxToolCalls === "number" && toolCalls >= input.maxToolCalls) {
          traces.push(`tool-budget: skipped ${tc.name}`)
          toolResultMessages.push({
            role: "tool",
            content: `[错误] 工具调用额度已用尽（上限 ${input.maxToolCalls} 次），未执行 ${tc.name}。`,
            toolCallId: tc.id,
            toolName: tc.name,
          })
          continue
        }
        const def = input.ports.findTool(tc.name)
        if (!def) {
          logger.warn(
            `[conversation-loop] Unknown tool '${tc.name}' at iteration ${iteration}; pushing error result`,
          )
          // D69 T3 (audit #10 CQ-19): Chinese owner-jargon phrasing in the
          // tool-result message so the LLM doesn't echo raw `unknown tool`
          // English to the owner. Mirrors D48 §4 owner-facing contract.
          // Phase 7 fix F1: include the advertised tool names so a model that
          // invented a tool (often a decision tag like `StartChildRun`) can
          // self-correct on the next iteration instead of burning the whole
          // turn budget on the same unknown name.
          traces.push(`unknown tool: ${tc.name}`)
          const availableNames = input.llmTools.map((t) => t.name)
          const availableTools = availableNames.join(", ") || "（无）"
          // Phase 7 fix F7: a model that invented a near-miss name (e.g.
          // `list_files` when the tool is `list_dir`) can recover from a
          // "did you mean" hint far faster than from the full list alone.
          const suggestion = suggestToolName(tc.name, availableNames)
          const isDecisionTag = (
            ["Respond", "Finish", "StartChildRun", "WaitForApproval", "CallCapability"] as const
          ).includes(tc.name as never)
          toolResultMessages.push({
            role: "tool",
            content: isDecisionTag
              ? `[错误] "${tc.name}" 是决策标签，不是工具；启动子任务请调用 delegate_to_subagent。可用工具：${availableTools}。`
              : `[错误] 未注册的工具：${tc.name}。${suggestion ? `你是不是想用 ${suggestion}？` : ""}可用工具：${availableTools}。请只调用这些工具。`,
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
        // F27 hard cap also applies to native `delegate_to_subagent` tool
        // calls — the model usually delegates this way, not via the
        // StartChildRun decision, so guarding only that path let a single
        // turn enqueue several child runs.
        if (
          tc.name === "delegate_to_subagent" &&
          typeof input.maxDelegationsPerTurn === "number" &&
          delegations >= input.maxDelegationsPerTurn
        ) {
          traces.push(
            `delegation-cap: refused ${tc.name} (max=${input.maxDelegationsPerTurn})`,
          )
          toolResultMessages.push({
            role: "tool",
            content: `[system] 本轮已派发 ${delegations} 个子任务（上限 ${input.maxDelegationsPerTurn}），不再启动新的子任务。请直接向 owner 汇报当前进展并结束本轮。`,
            toolCallId: tc.id,
            toolName: tc.name,
          })
          continue
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
        if (toolResult.ok && tc.name === "delegate_to_subagent") delegations += 1
        traces.push(
          `${tc.name}@${iteration}: ${
            toolResult.ok
              ? summarizeForLog(String(toolResult.output))
              : `error: ${toolResult.reason}`
          }`,
        )
        toolResultMessages.push({
          role: "tool",
          content: toolResult.ok
            ? formatToolOutput(toolResult.output)
            : `[error] ${toolResult.reason}`,
          toolCallId: tc.id,
          toolName: tc.name,
        })
      }
      messages.push(...toolResultMessages)
      continue
    }

    const raw = response.content.trim()
    if (raw) lastNonEmptyRaw = raw
    // 空内容重试：没有文本也没有 tool call 时，decode 只会返回 invalid JSON
    // 并最终落到 stub。最后一轮不再重试，保持既有收敛语义。
    if (!raw && !isFinalIteration && emptyContentRetries < maxEmptyContentRetries) {
      emptyContentRetries += 1
      messages.push({
        role: "user",
        content:
          "[system] empty-response: 上一次返回既没有文本也没有工具调用。请重新输出一个决策 JSON" +
          "（Respond / CallCapability / WaitForApproval / Finish 之一），不要返回空内容。",
      })
      traces.push(`empty content retry ${emptyContentRetries}/${maxEmptyContentRetries}`)
      continue
    }
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
      // Phase 7 fix F11/F36: never accept "已派子代理" prose as a finished turn —
      // unless a delegation actually started earlier in this loop run. Nudge once.
      const delegationClaim = looksLikeDelegationClaim(raw)
      if (
        input.delegationClaimGuard === true &&
        delegationClaim &&
        delegations === 0 &&
        !isFinalIteration &&
        !toolsExhausted &&
        delegationClaimNudges < 1
      ) {
        delegationClaimNudges += 1
        messages.push({ role: "user", content: DELEGATION_CLAIM_NUDGE })
        traces.push("delegation-claim nudge 1/1")
        continue
      }
      // Phase 7 fix F2b: a tool-first loop treats an early prose reply as
      // unfinished work — one or two nudges beat silently ending the run.
      // F19: when the tool budget is already exhausted the nudge is
      // self-contradictory (no tools are advertised on the next turn) and
      // costs two extra LLM calls; accept the summary instead.
      if (
        input.toolFirst === true &&
        input.llmTools.length > 0 &&
        !isFinalIteration &&
        !toolsExhausted &&
        toolFirstNudges < maxToolFirstNudges
      ) {
        toolFirstNudges += 1
        messages.push({
          role: "user",
          content:
            "[system] 任务还没完成：读取/查看文件只是准备动作，不是结果。请继续调用工具创建或修改任务要求的文件；全部落地后先用 list_files 核对，再给出纯文本总结。",
        })
        traces.push(`tool-first nudge ${toolFirstNudges}/${maxToolFirstNudges}`)
        continue
      }
      const respondContent = raw || lastNonEmptyRaw || input.ports.stubReply()
      const respondDecision: ModelDecision = {
        _tag: "Respond",
        content: respondContent,
      }
      await safeApplyDecision(input.kernel, respondDecision, logger)
      // This fallback is still a user-visible reply (the model ignored the
      // decision contract and answered in prose). Persist it like any other
      // Respond, otherwise history and redelivery replay cannot see it.
      if (input.ports.persistAssistantReply) {
        await input.ports.persistAssistantReply(respondContent)
      }
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
        const text = decision.content.trim()
        const reply = text || input.ports.stubReply()
        // Phase 7 fix F36: a structured Respond that merely claims a delegation
        // must not end the turn either — same guard as the plain-text path.
        if (
          input.delegationClaimGuard === true &&
          delegations === 0 &&
          !isFinalIteration &&
          !toolsExhausted &&
          delegationClaimNudges < 1 &&
          looksLikeDelegationClaim(reply)
        ) {
          delegationClaimNudges += 1
          messages.push({ role: "user", content: DELEGATION_CLAIM_NUDGE })
          traces.push("delegation-claim nudge 1/1")
          continue
        }
        await safeApplyDecision(input.kernel, decision, logger)
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
        if (typeof input.maxToolCalls === "number" && toolCalls >= input.maxToolCalls) {
          traces.push("tool-budget: skipped delegate_to_subagent")
          messages.push({
            role: "user",
            content: `[system] 工具调用额度已用尽（上限 ${input.maxToolCalls} 次），未启动子 Run。请直接给出答复或澄清。`,
          })
          continue
        }
        // F27 hard cap: one owner turn fanning out many child tasks burns
        // budget on repeated "verification" runs. Refuse past the cap and
        // ask the model to report instead of continuing to delegate.
        if (
          typeof input.maxDelegationsPerTurn === "number" &&
          delegations >= input.maxDelegationsPerTurn
        ) {
          traces.push(`delegation-cap: refused delegate_to_subagent (max=${input.maxDelegationsPerTurn})`)
          messages.push({
            role: "user",
            content: `[system] 本轮已派发 ${delegations} 个子任务（上限 ${input.maxDelegationsPerTurn}），不再启动新的子任务。请直接向 owner 汇报当前进展并结束本轮（Respond）。`,
          })
          continue
        }
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
        if (toolResult.ok) delegations += 1
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
          content: toolResult.ok
            ? formatToolOutput(toolResult.output)
            : `[error] ${toolResult.reason}`,
          toolCallId,
          toolName: "delegate_to_subagent",
        })
        continue
      }
      case "CallCapability": {
        await safeApplyDecision(input.kernel, decision, logger)
        if (typeof input.maxToolCalls === "number" && toolCalls >= input.maxToolCalls) {
          traces.push(`tool-budget: skipped ${decision.name}`)
          messages.push({
            role: "user",
            content: `[system] 工具调用额度已用尽（上限 ${input.maxToolCalls} 次），未执行 ${decision.name}。请直接给出答复或澄清。`,
          })
          continue
        }
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
          content: toolResult.ok
            ? formatToolOutput(toolResult.output)
            : `[error] ${toolResult.reason}`,
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
  const exhaustedReply = `[需要澄清] 模型未在 ${maxIterations} 轮内收敛，请补充信息或缩小范围。`
  // 用户确实收到了一条答复，所以语义上是 Respond，不是「无需回复」的 Finish。
  await safeApplyDecision(input.kernel, { _tag: "Respond", content: exhaustedReply }, logger)
  return {
    reply: exhaustedReply,
    iterations: maxIterations,
    toolCalls,
    finalDecision: "Respond",
    traces: [...traces, `loop exhausted (max=${maxIterations})`],
  }
}
