/**
 * Butler-layer model port.
 *
 * Deliberately narrower than the task-layer pi Agent: the butler runtime owns
 * its own loop, so the model only needs a chat-completion-shaped call. This
 * keeps the runtime testable without a provider and lets the app inject either
 * the existing LLM adapters or a pi-backed bridge later.
 */
import type { ButlerMessage, ButlerToolCall } from "@butler/ports/core/butler-session.js"

export interface ButlerTokenUsage {
  readonly inputTokens: number
  readonly outputTokens: number
  readonly totalTokens: number
}

export interface ButlerToolSpec {
  readonly name: string
  readonly description: string
  readonly parameters: {
    readonly type: "object"
    readonly properties?: Readonly<Record<string, unknown>>
    readonly required?: readonly string[]
  }
}

export interface ButlerModelReply {
  readonly content: string
  readonly toolCalls?: readonly ButlerToolCall[]
  readonly usage?: ButlerTokenUsage
}

export interface ButlerModelPort {
  complete(request: {
    readonly messages: readonly ButlerMessage[]
    readonly tools?: readonly ButlerToolSpec[]
  }): Promise<ButlerModelReply>
}

export const ZERO_USAGE: ButlerTokenUsage = {
  inputTokens: 0,
  outputTokens: 0,
  totalTokens: 0,
}

export const DEFAULT_BUTLER_SYSTEM_PROMPT =
  "你是 WFXM 微信管家。职责：理解用户意图、补全必要信息、把编码任务交给任务层。\n" +
  "- 简单问答直接回答；需要改代码或运行命令时调用 start_task。\n" +
  "- 不要编造任务状态；需要时调用 list_tasks 或 task_status。\n" +
  "- 不要输出内部字段名、JSON 或工具名，用中文简洁回复。"
