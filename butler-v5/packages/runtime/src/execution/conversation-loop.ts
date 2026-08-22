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

export const DEFAULT_MAX_LOOP_ITERATIONS = 5

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
      finalDecision: base.finalDecision ?? "AskApproval",
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
}): Promise<ConversationLoopResult> {
  const logger = input.ports.logger ?? defaultLogger
  const maxIterations = input.maxIterations ?? DEFAULT_MAX_LOOP_ITERATIONS
  const messages = [...input.messages]
  const traces: string[] = [...(input.initialTraces ?? [])]
  let toolCalls = 0
  let lastDecision: ModelDecision["_tag"] = "Finish"

  for (let iteration = 0; iteration < maxIterations; iteration++) {
    const outcome = await input.ports.complete(messages, input.llmTools)

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
          content: toolResult.ok ? String(toolResult.output) : `[error] ${toolResult.reason}`,
          toolCallId: tc.id,
          toolName: tc.name,
        })
      }
      messages.push(...toolResultMessages)
      continue
    }

    const raw = response.content.trim()
    const decoded = decodeDecision(raw)
    if (!decoded.ok) {
      logger.warn(
        `[conversation-loop] decodeDecision failed at iteration ${iteration}: ${decoded.reason}; treating as Respond`,
      )
      const respondDecision: ModelDecision = { _tag: "Respond", content: raw }
      await safeApplyDecision(input.kernel, respondDecision, logger)
      lastDecision = "Respond"
      return {
        reply: raw || input.ports.stubReply(),
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
      case "AskApproval": {
        await safeApplyDecision(input.kernel, decision, logger)
        return {
          reply: `[需要确认] ${decision.question}`,
          iterations: iteration + 1,
          toolCalls,
          finalDecision: "AskApproval",
          traces: [...traces, `AskApproval echoed: ${decision.question}`],
        }
      }
      case "Delegate": {
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
            finalDecision: "Delegate",
            traces,
          }
        }
        toolCalls += 1
        const toolResult = await executeToolInLoop({
          ports: input.ports,
          def,
          toolArgs: { task: decision.task, role: decision.role },
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
        await safeApplyDecision(input.kernel, decision, logger)
        const def = input.ports.findTool(decision.toolName)
        if (!def) {
          logger.warn(
            `[conversation-loop] Unknown tool '${decision.toolName}' at iteration ${iteration}; treating as Finish`,
          )
          traces.push(`unknown tool: ${decision.toolName}`)
          return {
            reply: input.ports.stubReply(),
            iterations: iteration + 1,
            toolCalls,
            finalDecision: "CallTool",
            traces,
          }
        }
        toolCalls += 1
        const toolResult = await executeToolInLoop({
          ports: input.ports,
          def,
          toolArgs: decision.args,
          iteration,
          toolCalls,
          traces,
          toolName: decision.toolName,
        })
        traces.push(
          `${decision.toolName}@${iteration}: ${
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
    `[conversation-loop] Loop exhausted after ${maxIterations} iterations; falling back to stub`,
  )
  await safeApplyDecision(input.kernel, { _tag: "Finish", reason: "loop exhausted" }, logger)
  return {
    reply: input.ports.stubReply(),
    iterations: maxIterations,
    toolCalls,
    finalDecision: lastDecision,
    traces: [...traces, `loop exhausted (max=${maxIterations})`],
  }
}
