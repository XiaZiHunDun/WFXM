/**
 * pi-backed conversation loop.
 *
 * Runs the vendored pi agent loop (`@butler/pi-agent`) while preserving the
 * existing Butler decision protocol:
 *
 * - JSON decisions (Respond / CallCapability / WaitForApproval / Finish) are
 *   decoded in `finishTurn`, exactly like `conversation-loop.ts`.
 * - Native provider tool calls are executed by pi through bridged `AgentTool`s,
 *   so both paths share the same policy / approval gate.
 * - Budget notes, final-iteration nudge, empty-content retry, decode retry and
 *   stuck-loop detection mirror the native loop.
 *
 * This engine is opt-in (`BUTLER_V5_LOOP_ENGINE=pi`) until the capability suite
 * confirms parity; the default stays native.
 */
import {
  agentLoop,
  type AgentEvent,
  type AgentLoopConfig,
  type AgentMessage,
  type AgentTool,
  type AgentToolCall,
  type StreamFn,
} from "@butler/pi-agent"
import {
  createAssistantMessageEventStream,
  type AssistantMessage,
  type Api,
  type JsonObject,
  type Model,
  type TextContent,
  type Usage,
} from "@earendil-works/pi-ai"
import type { AgentKernel } from "../agent-kernel.js"
import { decodeDecision, type ModelDecision } from "../decision.js"
import { RunPauseForApproval } from "../run-engine.js"
import type { RunResult, ToolDefinition } from "../tool-runtime.js"
import {
  DEFAULT_MAX_EMPTY_CONTENT_RETRIES,
  DEFAULT_STUCK_LOOP_THRESHOLD,
  resolveLoopIterations,
  type ConversationLoopLlmTool,
  type ConversationLoopLogger,
  type ConversationLoopMessage,
  type ConversationLoopPorts,
  type ConversationLoopResult,
} from "./conversation-loop.js"

/**
 * Keep the per-request text hint identical to the native loop. Duplicating the
 * string is deliberate: pi-engine is removable without touching native code.
 */
const FINAL_ITERATION_NUDGE =
  "这是最后一轮：不要调用任何工具。请直接给用户一个有用答复（Respond）；信息不足时用 Respond 提 1 个具体澄清问题，不要 Finish。"

const BUDGET_PREFIX = "工具预算："

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

const EMPTY_USAGE: Usage = {
  input: 0,
  output: 0,
  cacheRead: 0,
  cacheWrite: 0,
  totalTokens: 0,
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
}

const PLACEHOLDER_MODEL = {
  id: "butler",
  name: "butler",
  api: "openai-completions",
  provider: "openai",
  baseUrl: "",
  input: ["text"],
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
  contextWindow: 128_000,
  maxTokens: 8_192,
  reasoning: false,
} satisfies Model<Api>

function now(): number {
  return Date.now()
}

function textOf(message: AgentMessage): string {
  if (message.role !== "assistant") return ""
  return message.content
    .filter((block): block is TextContent => block.type === "text")
    .map((block) => block.text)
    .join("")
}

/** pi transcript -> Butler messages. Tool declarations live in pi system messages. */
function fromPiMessages(messages: readonly AgentMessage[]): ConversationLoopMessage[] {
  const out: ConversationLoopMessage[] = []
  for (const message of messages) {
    if (message.role === "system") {
      out.push({ role: "system", content: textOfSystem(message) })
    } else if (message.role === "user") {
      out.push({
        role: "user",
        content:
          typeof message.content === "string" ? message.content : textOfContent(message.content),
      })
    } else if (message.role === "assistant") {
      // Preserve native tool calls: the provider must see the assistant call
      // that the following toolResult answers, otherwise the transcript is
      // invalid and adapters drop the orphaned tool result.
      const toolCalls = message.content
        .filter((block): block is AgentToolCall => block.type === "toolCall")
        .map((call) => ({
          id: call.id,
          name: call.name,
          args: call.arguments as Record<string, unknown>,
        }))
      out.push(
        toolCalls.length > 0
          ? { role: "assistant", content: textOf(message), toolCalls }
          : { role: "assistant", content: textOf(message) },
      )
    } else if (message.role === "toolResult") {
      out.push({
        role: "tool",
        content: textOfContent(message.content),
        toolCallId: message.toolCallId,
        toolName: message.toolName,
      })
    }
  }
  return out
}

function textOfSystem(message: Extract<AgentMessage, { role: "system" }>): string {
  return typeof message.content === "string" ? message.content : textOfContent(message.content)
}

function textOfContent(content: readonly { type: string; text?: string }[]): string {
  return content
    .filter((block) => block.type === "text")
    .map((block) => block.text ?? "")
    .join("")
}

/** Butler messages -> pi transcript for the initial context. */
function toPiMessages(messages: readonly ConversationLoopMessage[]): AgentMessage[] {
  return messages.map((message): AgentMessage => {
    if (message.role === "system") {
      return { role: "system", content: message.content, timestamp: now() }
    }
    if (message.role === "user") {
      return { role: "user", content: message.content, timestamp: now() }
    }
    if (message.role === "assistant") {
      const content: AssistantMessage["content"] = message.content
        ? [{ type: "text", text: message.content }]
        : []
      for (const call of message.toolCalls ?? []) {
        content.push({
          type: "toolCall",
          id: call.id,
          name: call.name,
          arguments: call.args as JsonObject,
        })
      }
      return {
        role: "assistant",
        content,
        api: PLACEHOLDER_MODEL.api,
        provider: PLACEHOLDER_MODEL.provider,
        model: PLACEHOLDER_MODEL.id,
        usage: EMPTY_USAGE,
        stopReason: "stop",
        timestamp: now(),
      }
    }
    return {
      role: "toolResult",
      toolCallId: message.toolCallId ?? `call-${now()}`,
      toolName: message.toolName ?? "tool",
      content: [{ type: "text", text: message.content }],
      isError: false,
      timestamp: now(),
    }
  })
}

/**
 * `instanceof` can fail when the delivery shell and the runtime resolve
 * `run-engine` through different module instances (source vs dist, bundler
 * duplication). Fall back to the class name so an approval pause never gets
 * downgraded to a normal tool error.
 */
function isApprovalPause(error: unknown): error is RunPauseForApproval {
  if (error instanceof RunPauseForApproval) return true
  if (!(error instanceof Error)) return false
  // `name` stays "Error" (the class does not override it), so match the
  // constructor instead. The message is a last-resort guard for transpiled
  // copies that lose the class reference entirely.
  return (
    error.constructor?.name === "RunPauseForApproval" || error.message === "run paused for approval"
  )
}

interface ToolOutcome {
  readonly result?: RunResult
  readonly paused?: RunPauseForApproval
  readonly error?: string
}

export interface PiEngineInput {
  readonly kernel: AgentKernel
  readonly messages: readonly ConversationLoopMessage[]
  readonly llmTools: readonly ConversationLoopLlmTool[]
  readonly ports: ConversationLoopPorts
  readonly maxIterations?: number
  readonly maxToolCalls?: number
  readonly initialTraces?: readonly string[]
  readonly llmTimeoutMs?: number
  readonly stuckLoopThreshold?: number
  readonly maxEmptyContentRetries?: number
  readonly maxDecodeRetries?: number
}

export async function runPiConversationLoop(input: PiEngineInput): Promise<ConversationLoopResult> {
  const logger: ConversationLoopLogger =
    input.ports.logger ??
    ({
      // eslint-disable-next-line no-console -- intentional stderr log for operator debugging
      warn: (message, extra) => console.warn(message, extra ?? ""),
      // eslint-disable-next-line no-console -- intentional stderr log for operator debugging
      error: (message, error) => console.error(message, error),
    } satisfies ConversationLoopLogger)

  const maxIterations = resolveLoopIterations(input.maxIterations, input.maxToolCalls)
  const stuckLoopThreshold = input.stuckLoopThreshold ?? DEFAULT_STUCK_LOOP_THRESHOLD
  const maxEmptyContentRetries = input.maxEmptyContentRetries ?? DEFAULT_MAX_EMPTY_CONTENT_RETRIES
  const maxDecodeRetries = input.maxDecodeRetries ?? 1

  const traces: string[] = [...(input.initialTraces ?? [])]
  let toolCalls = 0
  let requestIndex = 0
  let emptyContentRetries = 0
  let decodeFailures = 0
  let firstDecodeFailureReason = ""
  let lastNonEmptyRaw = ""
  let pause: RunPauseForApproval | undefined
  let finalReply: string | undefined
  let finalDecision: ModelDecision["_tag"] = "Finish"
  let pendingMessages: AgentMessage[] = []
  const callSignatures = new Map<string, number>()
  let toolsForRequest: readonly ConversationLoopLlmTool[] = input.llmTools

  async function apply(decision: ModelDecision): Promise<void> {
    try {
      await input.kernel.applyDecision(decision)
    } catch (error) {
      logger.warn(
        `[pi-engine] applyDecision(${decision._tag}) failed; continuing:`,
        error instanceof Error ? error.message : String(error),
      )
    }
  }

  async function execute(
    def: ToolDefinition,
    args: Readonly<Record<string, unknown>>,
    iteration: number,
  ): Promise<ToolOutcome> {
    try {
      return { result: await input.ports.executeTool(def, args) }
    } catch (error) {
      if (isApprovalPause(error)) {
        pause = error
        traces.push(
          error instanceof RunPauseForApproval
            ? "pause detected via instanceof"
            : "pause detected via error name",
        )
        return { paused: error }
      }
      const reason = error instanceof Error ? error.message : String(error)
      traces.push(`tool error: ${reason}`)
      logger.warn(`[pi-engine] tool execution failed at iteration ${iteration}:`, reason)
      return { error: reason }
    }
  }

  /** Synthesize a terminal decision and stop the loop. */
  async function finish(tag: "Respond" | "Finish", content: string): Promise<void> {
    const decision: ModelDecision =
      tag === "Respond" ? { _tag: "Respond", content } : { _tag: "Finish", reason: content }
    await apply(decision)
    finalDecision = tag
    finalReply = content
  }

  const tools: AgentTool[] = input.llmTools.map((llmTool) => ({
    name: llmTool.name,
    label: llmTool.name,
    description: llmTool.description,
    parameters: llmTool.parameters as unknown as object,
    execute: async (_toolCallId, params) => {
      const def = input.ports.findTool(llmTool.name)
      if (!def) {
        traces.push(`unknown tool: ${llmTool.name}`)
        return {
          content: [{ type: "text", text: `[错误] 未注册的工具：${llmTool.name}` }],
          details: undefined,
          isError: true,
        }
      }
      if (typeof input.maxToolCalls === "number" && toolCalls >= input.maxToolCalls) {
        traces.push(`tool-budget: skipped ${llmTool.name}`)
        return {
          content: [
            {
              type: "text",
              text: `[错误] 工具调用额度已用尽（上限 ${input.maxToolCalls} 次），未执行 ${llmTool.name}。`,
            },
          ],
          details: undefined,
          isError: true,
          terminate: true,
        }
      }
      toolCalls += 1
      const outcome = await execute(def, params as Record<string, unknown>, requestIndex)
      if (outcome.paused) {
        return {
          content: [{ type: "text", text: "需要审批后才能继续。" }],
          details: undefined,
          isError: false,
          terminate: true,
        }
      }
      if (outcome.error) {
        return {
          content: [{ type: "text", text: `[error] ${outcome.error}` }],
          details: undefined,
          isError: true,
        }
      }
      const result = outcome.result
      if (!result) {
        return {
          content: [{ type: "text", text: "[error] 工具未返回结果" }],
          details: undefined,
          isError: true,
        }
      }
      traces.push(
        `${llmTool.name}@${requestIndex}: ${
          result.ok ? summarize(String(result.output)) : `error: ${result.reason}`
        }`,
      )
      return {
        content: [
          {
            type: "text",
            text: result.ok ? formatOutput(result.output) : `[error] ${result.reason}`,
          },
        ],
        details: undefined,
        isError: !result.ok,
      }
    },
  }))

  const streamFn: StreamFn = async (_model, context) => {
    const stream = createAssistantMessageEventStream()
    requestIndex += 1
    const messages = fromPiMessages(context.messages)
    const started = now()
    const outcome = await completeWithTimeout(
      () => input.ports.complete(messages, toolsForRequest),
      input.llmTimeoutMs ?? 30_000,
    )
    if (!outcome.ok) {
      const errorMessage: AssistantMessage = {
        role: "assistant",
        content: [],
        api: PLACEHOLDER_MODEL.api,
        provider: PLACEHOLDER_MODEL.provider,
        model: PLACEHOLDER_MODEL.id,
        usage: EMPTY_USAGE,
        stopReason: "error",
        errorMessage: outcome.reason,
        timestamp: started,
      }
      stream.push({ type: "error", reason: "error", error: errorMessage })
      return stream
    }

    const response = outcome.response
    const content: AssistantMessage["content"] = []
    if (response.content) content.push({ type: "text", text: response.content })
    for (const call of response.toolCalls) {
      content.push({
        type: "toolCall",
        id: call.id,
        name: call.name,
        arguments: call.args as JsonObject,
      })
    }
    const message: AssistantMessage = {
      role: "assistant",
      content,
      api: PLACEHOLDER_MODEL.api,
      provider: PLACEHOLDER_MODEL.provider,
      model: PLACEHOLDER_MODEL.id,
      usage: {
        ...EMPTY_USAGE,
        input: response.usage?.inputTokens ?? 0,
        output: response.usage?.outputTokens ?? 0,
        totalTokens: response.usage?.totalTokens ?? 0,
      },
      stopReason: response.toolCalls.length > 0 ? "toolUse" : "stop",
      timestamp: started,
    }
    stream.push({ type: "start", partial: message })
    if (response.content) {
      stream.push({ type: "text_start", contentIndex: 0, partial: message })
      stream.push({
        type: "text_delta",
        contentIndex: 0,
        delta: response.content,
        partial: message,
      })
      stream.push({
        type: "text_end",
        contentIndex: 0,
        content: response.content,
        partial: message,
      })
    }
    stream.push({
      type: "done",
      reason: response.toolCalls.length > 0 ? "toolUse" : "stop",
      message,
    })
    return stream
  }

  const config: AgentLoopConfig = {
    model: PLACEHOLDER_MODEL,
    convertToLlm: (messages) => messages as never,
    toolExecution: "sequential",
    prepareRequest: ({ context }) => {
      const final = requestIndex >= maxIterations - 1
      const exhausted = typeof input.maxToolCalls === "number" && toolCalls >= input.maxToolCalls
      toolsForRequest = final || exhausted ? [] : input.llmTools

      // Keep exactly one budget note, at the tail.
      for (let i = context.messages.length - 1; i >= 0; i -= 1) {
        const message = context.messages[i]
        if (
          message?.role === "system" &&
          typeof message.content === "string" &&
          message.content.startsWith(BUDGET_PREFIX)
        ) {
          context.messages.splice(i, 1)
        }
      }
      if (typeof input.maxToolCalls === "number") {
        context.messages.push({
          role: "system",
          content: toolBudgetNote(input.maxToolCalls, toolCalls),
          timestamp: now(),
        })
      }
      if (final && input.llmTools.length > 0) {
        context.messages.push({
          role: "system",
          content: FINAL_ITERATION_NUDGE,
          timestamp: now(),
        })
      }
    },
    prepareNextTurn: () => {
      if (pendingMessages.length === 0) return undefined
      const messages = pendingMessages
      pendingMessages = []
      return { messages }
    },
    finishTurn: async (turn) => {
      if (pause) return { action: "end" }

      // Native provider tool calls were already executed by pi (our bridged
      // AgentTool wrappers). Their text may be empty, so never run the JSON
      // decoder on this turn — just let the loop continue to the next request.
      if (
        turn.message.role === "assistant" &&
        turn.message.content.some((c) => c.type === "toolCall")
      ) {
        return { action: "continue" }
      }

      const raw = textOf(turn.message).trim()
      if (raw) lastNonEmptyRaw = raw

      if (!raw && emptyContentRetries < maxEmptyContentRetries && requestIndex < maxIterations) {
        emptyContentRetries += 1
        pendingMessages.push({
          role: "user",
          content:
            "[system] empty-response: 上一次返回既没有文本也没有工具调用。请重新输出一个决策 JSON" +
            "（Respond / CallCapability / WaitForApproval / Finish 之一），不要返回空内容。",
          timestamp: now(),
        })
        traces.push(`empty content retry ${emptyContentRetries}/${maxEmptyContentRetries}`)
        return { action: "continue" }
      }

      const decoded = decodeDecision(raw)
      if (!decoded.ok) {
        if (!firstDecodeFailureReason) firstDecodeFailureReason = decoded.reason
        decodeFailures += 1
        const structured = decoded.reason !== "invalid JSON"
        if (structured && decodeFailures <= maxDecodeRetries) {
          pendingMessages.push({
            role: "user",
            content: `[system] decision-decode-fail: ${decoded.reason}. If a Decision was intended, retry with valid JSON. Raw reply was: \`\`\`${raw.slice(0, 200)}\`\`\``,
            timestamp: now(),
          })
          traces.push(
            `decode failed retry ${decodeFailures}/${maxDecodeRetries}: ${decoded.reason}`,
          )
          return { action: "continue" }
        }
        const fallback = raw || lastNonEmptyRaw || input.ports.stubReply()
        await finish("Respond", fallback)
        traces.push(`decode fallback: ${decoded.reason}`)
        return { action: "end" }
      }

      const decision = decoded.value
      if (decision._tag === "Respond") {
        await apply(decision)
        finalDecision = "Respond"
        finalReply = decision.content
        return { action: "end" }
      }
      if (decision._tag === "Finish") {
        await apply(decision)
        finalDecision = "Finish"
        finalReply = input.ports.stubReply()
        return { action: "end" }
      }
      if (decision._tag === "WaitForApproval") {
        await apply(decision)
        finalDecision = "WaitForApproval"
        finalReply = decision.question
        return { action: "end" }
      }
      if (decision._tag === "StartChildRun") {
        // Delegation is not wired into the pi engine in Phase 2; surface it
        // instead of silently miscounting it as a normal answer.
        traces.push("unsupported decision: StartChildRun")
        await finish("Finish", "子任务委派暂未接入 pi 引擎。")
        return { action: "end" }
      }

      // CallCapability through the JSON protocol.
      if (requestIndex >= maxIterations) {
        traces.push(`iteration cap: ignored CallCapability ${decision.name}`)
        await finish("Finish", input.ports.stubReply())
        return { action: "end" }
      }
      if (typeof input.maxToolCalls === "number" && toolCalls >= input.maxToolCalls) {
        traces.push(`tool-budget: skipped ${decision.name}`)
        pendingMessages.push({
          role: "toolResult",
          toolCallId: decision.callId ?? `call-${now()}`,
          toolName: decision.name,
          content: [
            {
              type: "text",
              text: `[错误] 工具调用额度已用尽（上限 ${input.maxToolCalls} 次），未执行 ${decision.name}。`,
            },
          ],
          isError: true,
          timestamp: now(),
        })
        return { action: "continue" }
      }
      const def = input.ports.findTool(decision.name)
      if (!def) {
        traces.push(`unknown tool: ${decision.name}`)
        pendingMessages.push({
          role: "toolResult",
          toolCallId: decision.callId ?? `call-${now()}`,
          toolName: decision.name,
          content: [{ type: "text", text: `[错误] 未注册的工具：${decision.name}` }],
          isError: true,
          timestamp: now(),
        })
        return { action: "continue" }
      }
      const signature = `${decision.name}:${JSON.stringify(decision.arguments)}`
      const seen = (callSignatures.get(signature) ?? 0) + 1
      callSignatures.set(signature, seen)
      if (seen >= stuckLoopThreshold) {
        const reason = `stuck-loop: ${decision.name} invoked ${seen}x with same args; aborting`
        traces.push(reason)
        await apply({ _tag: "Finish", reason: `stuck-loop: ${decision.name}` })
        finalDecision = "Finish"
        finalReply = input.ports.stubReply()
        return { action: "end" }
      }

      toolCalls += 1
      const outcome = await execute(def, decision.arguments, requestIndex)
      if (outcome.paused) return { action: "end" }
      toolsForRequest = input.llmTools
      if (outcome.error) {
        pendingMessages.push({
          role: "toolResult",
          toolCallId: decision.callId ?? `call-${now()}`,
          toolName: decision.name,
          content: [{ type: "text", text: `[error] ${outcome.error}` }],
          isError: true,
          timestamp: now(),
        })
        return { action: "continue" }
      }
      const result = outcome.result
      if (!result) {
        pendingMessages.push({
          role: "toolResult",
          toolCallId: decision.callId ?? `call-${now()}`,
          toolName: decision.name,
          content: [{ type: "text", text: "[error] 工具未返回结果" }],
          isError: true,
          timestamp: now(),
        })
        return { action: "continue" }
      }
      traces.push(
        `${decision.name}@${requestIndex}: ${
          result.ok ? summarize(String(result.output)) : `error: ${result.reason}`
        }`,
      )
      pendingMessages.push({
        role: "toolResult",
        toolCallId: decision.callId ?? `call-${now()}`,
        toolName: decision.name,
        content: [
          {
            type: "text",
            text: result.ok ? formatOutput(result.output) : `[error] ${result.reason}`,
          },
        ],
        isError: !result.ok,
        timestamp: now(),
      })
      return { action: "continue" }
    },
  }

  try {
    const stream = agentLoop(
      [],
      { messages: toPiMessages(input.messages), tools },
      config,
      undefined,
      streamFn,
    )
    for await (const event of stream) {
      collectTrace(event, traces)
    }
    await stream.result()
  } catch (error) {
    traces.push(`pi engine error: ${error instanceof Error ? error.message : String(error)}`)
    logger.error("[pi-engine] loop failed; falling back to stub reply", error)
    finalDecision = "Finish"
    finalReply = input.ports.stubReply()
  }

  if (pause) throw pause
  if (finalReply === undefined) {
    finalDecision = "Finish"
    finalReply = input.ports.stubReply()
    if (firstDecodeFailureReason) traces.push(`decode failed: ${firstDecodeFailureReason}`)
  }

  return {
    reply: finalReply,
    iterations: requestIndex,
    toolCalls,
    finalDecision,
    traces,
  } satisfies ConversationLoopResult
}

function collectTrace(event: AgentEvent, traces: string[]): void {
  if (event.type === "tool_execution_end") {
    traces.push(`pi.tool:${event.toolName}:${event.isError ? "error" : "ok"}`)
  } else if (event.type === "turn_end") {
    traces.push(`pi.turn.end`)
  }
}

function summarize(text: string, max = 80): string {
  return text.length <= max ? text : `${text.slice(0, max - 3)}...`
}

function formatOutput(output: unknown): string {
  return typeof output === "string" ? output : JSON.stringify(output)
}

async function completeWithTimeout(
  invoke: () => ReturnType<ConversationLoopPorts["complete"]>,
  timeoutMs: number,
): Promise<
  | Awaited<ReturnType<ConversationLoopPorts["complete"]>>
  | { readonly ok: false; readonly reason: string }
> {
  let timer: NodeJS.Timeout | undefined
  const timeout = new Promise<{ readonly ok: false; readonly reason: string }>((resolve) => {
    timer = setTimeout(
      () => resolve({ ok: false, reason: `LLM timeout after ${timeoutMs}ms` }),
      timeoutMs,
    )
  })
  try {
    return await Promise.race([invoke(), timeout])
  } finally {
    if (timer) clearTimeout(timer)
  }
}
