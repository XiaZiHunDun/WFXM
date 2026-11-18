/**
 * P4.1 pi-native task runner.
 *
 * One task = one session bound to `taskId + projectId + cwd`. The runner is
 * stateless between turns: the Agent is rebuilt from a JSON snapshot, so a
 * paused task can be persisted by the butler layer and resumed in another
 * process. A process-wide FIFO lock keeps a single active Agent.
 */
import { realpath, stat } from "node:fs/promises"
import {
  Agent,
  type AgentMessage,
  type AgentTool,
  type AgentToolResult,
  type StreamFn,
} from "@butler/pi-agent"
import type { Api, Model } from "@earendil-works/pi-ai"
import type {
  PiTaskPendingStep,
  PiTaskSessionRecord,
  PiTaskSessionStatus,
  PiTaskSessionStore,
} from "@butler/ports/core/pi-task-session.js"
import type { TaskMemoryEvent, TaskMemoryPort } from "@butler/ports/core/task-memory.js"
import { createPiNativeTools } from "./pi-native-tools.js"
import { createPiStreamFn } from "./pi-model.js"
import { DEFAULT_PI_TASK_SYSTEM_PROMPT } from "./pi-task-prompt.js"
import { normalizePiToolName } from "./pi-tool-name-map.js"

export { DEFAULT_PI_TASK_SYSTEM_PROMPT }

const DEFAULT_MAX_TOOL_CALLS = 24
const ALWAYS_APPROVAL_TOOLS = new Set(["write", "edit"])
const DESTRUCTIVE_BASH =
  /(^|[\s;&|])(rm|rmdir|unlink|shred|truncate|mv|dd)(\s|$)|-delete\b|\btee\b|\bsed\s+-i\b|\bperl\s+-i\b|(^|[^0-9&])>{1,2}(?!\s*\/dev\/null)/

/** bash is allowed for exploration/tests; destructive commands need approval. */
export function bashNeedsApproval(command: string): boolean {
  return DESTRUCTIVE_BASH.test(command)
}

export interface PiTaskOpenInput {
  readonly taskId: string
  readonly projectId: string
  readonly cwd: string
  readonly summary?: string
  readonly systemPrompt?: string
}

export type PiApprovalCheck =
  { readonly required: true; readonly reason: string } | { readonly required: false }

export interface PiApprovalPolicy {
  check(input: {
    readonly toolName: string
    readonly args: unknown
    readonly cwd: string
  }): PiApprovalCheck | Promise<PiApprovalCheck>
}

export interface PiTaskToolCall {
  readonly toolCallId: string
  readonly rawName: string
  readonly normalizedName: string
  readonly args: Readonly<Record<string, unknown>>
  readonly ok: boolean
  readonly durationMs: number
  readonly output?: string
  readonly reason?: string
}

export interface PiTaskTurnResult {
  readonly taskId: string
  readonly status: PiTaskSessionStatus
  readonly reply: string
  readonly toolCalls: readonly PiTaskToolCall[]
  readonly pendingStep: PiTaskPendingStep | null
  readonly traces: readonly string[]
  readonly usage: {
    readonly inputTokens: number
    readonly outputTokens: number
    readonly totalTokens: number
  }
}

export interface PiTaskRunnerOptions {
  readonly model: Model<Api>
  readonly apiKey: string
  readonly streamFn?: StreamFn
  readonly temperature?: number
  readonly maxRetries?: number
  readonly baseDelayMs?: number
  readonly tools?: readonly AgentTool[]
  readonly approvalPolicy?: PiApprovalPolicy
  readonly maxToolCalls?: number
  readonly store?: PiTaskSessionStore
  /** Optional memory projection; the task layer never owns a memory store. */
  readonly memory?: TaskMemoryPort
  readonly systemPrompt?: string
  readonly logger?: { warn(message: string, extra?: unknown): void }
  readonly lock?: GlobalAgentLock
}

export class PiTaskBusyError extends Error {
  constructor(taskId: string, reason: string) {
    super(`task ${taskId} is busy: ${reason}`)
    this.name = "PiTaskBusyError"
  }
}

/** Process-wide FIFO lock: one active Agent, everyone else waits. */
export class GlobalAgentLock {
  private tail: Promise<void> = Promise.resolve()
  private active: string | null = null
  private waiting = 0

  constructor(public readonly name = "pi-agent-global") {}

  get activeTaskId(): string | null {
    return this.active
  }

  get queueLength(): number {
    return this.waiting
  }

  async run<T>(taskId: string, fn: () => Promise<T>): Promise<T> {
    this.waiting += 1
    let release: () => void = () => undefined
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    const previous = this.tail
    this.tail = previous.then(() => gate)
    try {
      await previous
      this.waiting -= 1
      this.active = taskId
      return await fn()
    } finally {
      this.active = null
      release()
    }
  }
}

export const globalAgentLock = new GlobalAgentLock()

export class MemoryPiTaskSessionStore implements PiTaskSessionStore {
  private readonly records = new Map<string, PiTaskSessionRecord>()

  async load(taskId: string): Promise<PiTaskSessionRecord | null> {
    return this.records.get(taskId) ?? null
  }

  async save(record: PiTaskSessionRecord): Promise<void> {
    this.records.set(record.taskId, record)
  }

  async delete(taskId: string): Promise<void> {
    this.records.delete(taskId)
  }
}

export function createDefaultApprovalPolicy(
  env: NodeJS.ProcessEnv = process.env,
): PiApprovalPolicy {
  const mode = (env["BUTLER_V5_PI_APPROVAL"] ?? "").trim().toLowerCase()
  return {
    check: ({ toolName, args }) => {
      if (mode === "never") return { required: false }
      if (mode === "always") {
        return { required: true, reason: "该操作需要你确认。" }
      }
      if (ALWAYS_APPROVAL_TOOLS.has(toolName)) {
        return { required: true, reason: "修改文件前需要你确认。" }
      }
      if (toolName === "bash") {
        const command =
          args && typeof args === "object" && "command" in args
            ? String((args as { command?: unknown }).command ?? "")
            : ""
        if (bashNeedsApproval(command)) {
          return { required: true, reason: "命令可能修改或删除文件，需要你确认。" }
        }
      }
      return { required: false }
    },
  }
}

interface SessionState {
  record: PiTaskSessionRecord
  running: boolean
  pauseRequested: boolean
  activeAgent?: Agent
}

interface TurnOptions {
  readonly timeoutMs?: number
  /** undefined = normal turn; true/false = resume a pending approval. */
  readonly approved?: boolean
  readonly approvalNote?: string
}

function nowIso(): string {
  return new Date().toISOString()
}

function cloneMessages(messages: readonly AgentMessage[]): readonly unknown[] {
  return JSON.parse(JSON.stringify(messages)) as unknown[]
}

function parseMessages(raw: readonly unknown[]): AgentMessage[] {
  const parsed = JSON.parse(JSON.stringify(raw)) as unknown
  if (!Array.isArray(parsed)) throw new Error("session snapshot messages must be an array")
  return parsed as AgentMessage[]
}

function textOfAssistant(message: AgentMessage): string {
  if (message.role !== "assistant") return ""
  return message.content
    .filter((block): block is { type: "text"; text: string } => block.type === "text")
    .map((block) => block.text)
    .join("")
}

function lastAssistantText(messages: readonly AgentMessage[]): string {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index]
    if (message && message.role === "assistant") {
      const text = textOfAssistant(message).trim()
      if (text) return text
    }
  }
  return ""
}

function lastUserText(messages: readonly AgentMessage[]): string {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index]
    if (message && message.role === "user") {
      const text = textOfUser(message).trim()
      if (text) return text
    }
  }
  return ""
}

function resultText(result: AgentToolResult<unknown>): string {
  return result.content
    .filter((block): block is { type: "text"; text: string } => block.type === "text")
    .map((block) => block.text)
    .join("")
}

function usageOf(messages: readonly AgentMessage[]): {
  inputTokens: number
  outputTokens: number
  totalTokens: number
} {
  let inputTokens = 0
  let outputTokens = 0
  let totalTokens = 0
  for (const message of messages) {
    if (message.role !== "assistant") continue
    inputTokens += message.usage.input
    outputTokens += message.usage.output
    totalTokens += message.usage.totalTokens
  }
  return { inputTokens, outputTokens, totalTokens }
}

const TEST_COMMAND_PATTERN =
  /\b(?:vitest|jest|mocha|node\s+--test|pnpm\s+(?:run\s+)?test|npm\s+(?:run\s+)?test|yarn\s+test)\b/

function textOfUser(message: AgentMessage): string {
  const content = (message as { content?: unknown }).content
  if (typeof content === "string") return content
  if (!Array.isArray(content)) return ""
  return content
    .filter(
      (block): block is { type: "text"; text: string } =>
        typeof block === "object" &&
        block !== null &&
        (block as { type?: unknown }).type === "text" &&
        typeof (block as { text?: unknown }).text === "string",
    )
    .map((block) => block.text)
    .join("")
}

function changedFilesOf(toolCalls: readonly PiTaskToolCall[]): string[] {
  const files = new Set<string>()
  for (const call of toolCalls) {
    if (!call.ok || (call.rawName !== "write" && call.rawName !== "edit")) continue
    const path = call.args["path"]
    if (typeof path === "string" && path.trim()) files.add(path)
  }
  return [...files]
}

function testResultOf(toolCalls: readonly PiTaskToolCall[]): TaskMemoryEvent["tests"] | undefined {
  for (let index = toolCalls.length - 1; index >= 0; index -= 1) {
    const call = toolCalls[index]
    if (!call || call.rawName !== "bash") continue
    const command = call.args["command"]
    if (typeof command !== "string" || !TEST_COMMAND_PATTERN.test(command)) continue
    return { command, passed: call.ok }
  }
  return undefined
}

function replaceToolResult(
  messages: readonly AgentMessage[],
  pending: PiTaskPendingStep,
  text: string,
  isError: boolean,
): AgentMessage[] {
  let replaced = false
  const next = messages.map((message) => {
    if (message.role !== "toolResult" || message.toolCallId !== pending.toolCallId) return message
    replaced = true
    return {
      ...message,
      content: [{ type: "text" as const, text }],
      isError,
      timestamp: Date.now(),
    } satisfies AgentMessage
  })
  if (replaced) return next
  return [
    ...next,
    {
      role: "toolResult",
      toolCallId: pending.toolCallId,
      toolName: pending.toolName,
      content: [{ type: "text", text }],
      isError,
      timestamp: Date.now(),
    } satisfies AgentMessage,
  ]
}

/**
 * Aborting at the approval point means later calls from the same assistant
 * message never run and never get a tool result. Fill them in explicitly so the
 * next model turn sees "not executed" instead of a silently dropped call (and
 * so the transcript stays valid for OpenAI-compatible APIs).
 */
function completeDanglingToolResults(messages: readonly AgentMessage[]): AgentMessage[] {
  let assistantIndex = -1
  let calls: { id: string; name: string }[] = []
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index]
    if (!message || message.role !== "assistant") continue
    const found: { id: string; name: string }[] = []
    for (const block of message.content) {
      if (block.type === "toolCall") found.push({ id: block.id, name: block.name })
    }
    if (found.length > 0) {
      assistantIndex = index
      calls = found
      break
    }
  }
  if (assistantIndex === -1) return [...messages]

  const answered = new Set(
    messages
      .slice(assistantIndex + 1)
      .filter((message) => message.role === "toolResult")
      .map((message) => message.toolCallId),
  )
  const missing = calls.filter((call) => !answered.has(call.id))
  if (missing.length === 0) return [...messages]

  const synthetic = missing.map(
    (call) =>
      ({
        role: "toolResult",
        toolCallId: call.id,
        toolName: call.name,
        content: [{ type: "text", text: "等待审批，本步未执行；如仍需要请重新发起该调用。" }],
        isError: true,
        timestamp: Date.now(),
      }) satisfies AgentMessage,
  )

  // Insert after the results that already belong to this batch, keeping the
  // transcript ordered (an aborted run may have appended a later message).
  let insertAt = assistantIndex + 1
  for (let index = messages.length - 1; index > assistantIndex; index -= 1) {
    if (messages[index]?.role === "toolResult") {
      insertAt = index + 1
      break
    }
  }
  return [...messages.slice(0, insertAt), ...synthetic, ...messages.slice(insertAt)]
}

export class PiTaskRunner {
  private readonly sessions = new Map<string, SessionState>()
  private readonly store: PiTaskSessionStore
  private readonly policy: PiApprovalPolicy
  private readonly lock: GlobalAgentLock
  private readonly streamFn: StreamFn
  private readonly maxToolCalls: number
  private readonly logger: { warn(message: string, extra?: unknown): void }

  constructor(private readonly options: PiTaskRunnerOptions) {
    this.store = options.store ?? new MemoryPiTaskSessionStore()
    this.policy = options.approvalPolicy ?? createDefaultApprovalPolicy()
    this.lock = options.lock ?? globalAgentLock
    this.maxToolCalls = options.maxToolCalls ?? DEFAULT_MAX_TOOL_CALLS
    this.streamFn =
      options.streamFn ??
      createPiStreamFn({
        model: options.model as Model<"openai-completions">,
        apiKey: options.apiKey,
        ...(options.temperature === undefined ? {} : { temperature: options.temperature }),
        ...(options.maxRetries === undefined ? {} : { maxRetries: options.maxRetries }),
        ...(options.baseDelayMs === undefined ? {} : { baseDelayMs: options.baseDelayMs }),
      })
    this.logger = options.logger ?? {
      warn: (message, extra) => {
        // eslint-disable-next-line no-console -- operator-facing warning
        console.warn(message, extra ?? "")
      },
    }
  }

  async open(input: PiTaskOpenInput): Promise<PiTaskSessionRecord> {
    if (this.sessions.has(input.taskId) || (await this.store.load(input.taskId))) {
      throw new PiTaskBusyError(input.taskId, "session already exists")
    }
    let cwd: string
    try {
      cwd = await realpath(input.cwd)
      const info = await stat(cwd)
      if (!info.isDirectory()) throw new Error("cwd is not a directory")
    } catch (error) {
      throw new Error(
        `cannot open task ${input.taskId}: ${error instanceof Error ? error.message : String(error)}`,
      )
    }
    const timestamp = nowIso()
    const record: PiTaskSessionRecord = {
      taskId: input.taskId,
      projectId: input.projectId,
      cwd,
      status: "idle",
      snapshot: {
        version: 1,
        systemPrompt:
          input.systemPrompt ?? this.options.systemPrompt ?? DEFAULT_PI_TASK_SYSTEM_PROMPT,
        ...(input.summary === undefined ? {} : { summary: input.summary }),
        messages: [],
      },
      pendingStep: null,
      createdAt: timestamp,
      updatedAt: timestamp,
    }
    await this.store.save(record)
    this.sessions.set(input.taskId, {
      record,
      running: false,
      pauseRequested: false,
    })
    return record
  }

  async load(taskId: string): Promise<PiTaskSessionRecord | null> {
    const cached = this.sessions.get(taskId)
    if (cached) return cached.record
    const record = await this.store.load(taskId)
    if (record) {
      this.sessions.set(taskId, { record, running: false, pauseRequested: false })
    }
    return record
  }

  async start(
    taskId: string,
    prompt: string,
    opts?: { timeoutMs?: number },
  ): Promise<PiTaskTurnResult> {
    const session = await this.requireSession(taskId)
    if (session.running) throw new PiTaskBusyError(taskId, "already running")
    return this.lock.run(taskId, () => this.runTurn(session, prompt, opts ?? {}))
  }

  async resume(
    taskId: string,
    decision: { readonly approved: boolean; readonly note?: string },
  ): Promise<PiTaskTurnResult> {
    const session = await this.requireSession(taskId)
    if (session.running) throw new PiTaskBusyError(taskId, "already running")
    return this.lock.run(taskId, () =>
      this.runTurn(
        session,
        decision.approved
          ? "审批已通过，请继续完成任务。"
          : "用户拒绝执行上一步操作，请不要重复该操作，改用其他方式或向用户说明。",
        {
          approved: decision.approved,
          ...(decision.note === undefined ? {} : { approvalNote: decision.note }),
        },
      ),
    )
  }

  async pause(taskId: string, reason = "用户暂停"): Promise<void> {
    const session = await this.requireSession(taskId)
    session.pauseRequested = true
    session.activeAgent?.abort()
    const record: PiTaskSessionRecord = {
      ...session.record,
      status: "paused",
      snapshot: {
        ...session.record.snapshot,
        messages: session.activeAgent
          ? cloneMessages(session.activeAgent.state.messages)
          : session.record.snapshot.messages,
      },
      updatedAt: nowIso(),
    }
    this.logger.warn(`[pi-task-runner] pause ${taskId}: ${reason}`)
    await this.save(session, record)
  }

  async close(taskId: string): Promise<void> {
    const session = this.sessions.get(taskId)
    session?.activeAgent?.abort()
    this.sessions.delete(taskId)
    await this.store.delete(taskId)
  }

  list(): readonly PiTaskSessionRecord[] {
    return [...this.sessions.values()].map((session) => session.record)
  }

  private async requireSession(taskId: string): Promise<SessionState> {
    const cached = this.sessions.get(taskId)
    if (cached) return cached
    const record = await this.store.load(taskId)
    if (!record) throw new Error(`task session not found: ${taskId}`)
    const session: SessionState = { record, running: false, pauseRequested: false }
    this.sessions.set(taskId, session)
    return session
  }

  private toolsFor(cwd: string): readonly AgentTool[] {
    return this.options.tools ?? createPiNativeTools({ cwd })
  }

  private buildAgent(session: SessionState, messages: AgentMessage[]): Agent {
    const record = session.record
    const tools = [...this.toolsFor(record.cwd)]
    return new Agent({
      initialState: {
        model: this.options.model,
        messages,
        tools,
        ...(messages.length === 0 ? { systemPrompt: record.snapshot.systemPrompt } : {}),
      },
      streamFn: this.streamFn,
      toolExecution: "sequential",
    })
  }

  private async save(session: SessionState, record: PiTaskSessionRecord): Promise<void> {
    session.record = record
    await this.store.save(record)
  }

  /**
   * Projects a finished turn into task memory. Failures are logged, never
   * surfaced to the caller: memory is an optimization, not a task dependency.
   */
  private async recordMemory(
    record: PiTaskSessionRecord,
    toolCalls: readonly PiTaskToolCall[],
    reply: string,
    status: PiTaskSessionStatus,
    goal: string,
  ): Promise<void> {
    const memory = this.options.memory
    if (!memory) return
    const changedFiles = changedFilesOf(toolCalls)
    const tests = testResultOf(toolCalls)
    try {
      await memory.recordTaskOutcome({
        taskId: record.taskId,
        projectId: record.projectId,
        goal,
        summary: reply,
        status: status === "failed" ? "failed" : "completed",
        ...(changedFiles.length > 0 ? { changedFiles } : {}),
        ...(tests === undefined ? {} : { tests }),
        occurredAt: record.updatedAt,
      })
    } catch (error) {
      this.logger.warn(`[pi-task-runner] ${record.taskId} memory projection failed`, error)
    }
  }

  private async runTurn(
    session: SessionState,
    prompt: string,
    opts: TurnOptions,
  ): Promise<PiTaskTurnResult> {
    if (session.record.pendingStep && opts.approved === undefined) {
      throw new Error(`task ${session.record.taskId} is paused; call resume instead of start`)
    }
    session.running = true
    session.pauseRequested = false
    let messages = parseMessages(session.record.snapshot.messages)
    let pending = session.record.pendingStep
    const traces: string[] = []
    const toolCalls: PiTaskToolCall[] = []

    // Resume: execute/deny the blocked step before rebuilding the Agent so the
    // transcript contains the real tool result exactly once.
    if (pending && opts.approved !== undefined) {
      const tool = this.toolsFor(session.record.cwd).find(
        (entry) => entry.name === pending?.toolName,
      )
      const started = Date.now()
      if (opts.approved) {
        try {
          if (!tool) throw new Error(`unknown pending tool: ${pending.toolName}`)
          const result = await tool.execute(pending.toolCallId, pending.args, undefined)
          const text = resultText(result)
          messages = replaceToolResult(messages, pending, text, result.isError === true)
          toolCalls.push({
            toolCallId: pending.toolCallId,
            rawName: pending.toolName,
            normalizedName: normalizePiToolName(pending.toolName),
            args: pending.args,
            ok: result.isError !== true,
            durationMs: Date.now() - started,
            output: text.slice(0, 2_000),
          })
          traces.push(`resume:${pending.toolName}:approved`)
        } catch (error) {
          const reason = error instanceof Error ? error.message : String(error)
          messages = replaceToolResult(messages, pending, `[error] ${reason}`, true)
          toolCalls.push({
            toolCallId: pending.toolCallId,
            rawName: pending.toolName,
            normalizedName: normalizePiToolName(pending.toolName),
            args: pending.args,
            ok: false,
            durationMs: Date.now() - started,
            reason,
          })
          traces.push(`resume:${pending.toolName}:failed:${reason}`)
        }
      } else {
        const note = opts.approvalNote?.trim()
        const text = note ? `用户拒绝执行该操作：${note}` : "用户拒绝执行该操作。"
        messages = replaceToolResult(messages, pending, text, true)
        traces.push(`resume:${pending.toolName}:denied`)
      }
      pending = null
      messages = completeDanglingToolResults(messages)
      traces.push("approval:pending-cleared")
    }

    const beforeCount = messages.length
    let pendingStep: PiTaskPendingStep | undefined
    let approvalRequested = false
    const agent = this.buildAgent(session, messages)
    // End the turn right after a batch that hit an approval gate, so the run
    // pauses deterministically instead of asking the model again.
    agent.finishTurn = async () => (pendingStep === undefined ? undefined : { action: "end" })
    session.activeAgent = agent
    let toolCount = 0
    const startedAt = new Map<string, number>()

    agent.beforeToolCall = async (context) => {
      if (toolCount >= this.maxToolCalls) {
        return {
          block: true,
          terminate: true,
          reason: `工具调用额度已用尽（上限 ${this.maxToolCalls} 次）`,
        }
      }
      if (approvalRequested) {
        // A later call from the same assistant message must not run before the
        // owner answers the first one.
        traces.push(`approval:deferred:${context.toolCall.name}`)
        return {
          block: true,
          reason: "等待审批，本步未执行；批准后请重新发起该调用。",
        }
      }
      const check = await this.policy.check({
        toolName: context.toolCall.name,
        args: context.args,
        cwd: session.record.cwd,
      })
      if (check.required) {
        pendingStep = {
          toolCallId: context.toolCall.id,
          toolName: context.toolCall.name,
          args: (context.args ?? {}) as Readonly<Record<string, unknown>>,
          reason: check.reason,
          requestedAt: nowIso(),
        }
        approvalRequested = true
        traces.push(`approval:required:${context.toolCall.name}`)
        return { block: true, terminate: true, reason: check.reason }
      }
      toolCount += 1
      startedAt.set(context.toolCall.id, Date.now())
      return undefined
    }

    agent.afterToolCall = async (context) => {
      const durationMs = Date.now() - (startedAt.get(context.toolCall.id) ?? Date.now())
      const text = resultText(context.result)
      toolCalls.push({
        toolCallId: context.toolCall.id,
        rawName: context.toolCall.name,
        normalizedName: normalizePiToolName(context.toolCall.name),
        args: (context.args ?? {}) as Readonly<Record<string, unknown>>,
        ok: !context.isError,
        durationMs,
        ...(text ? { output: text.slice(0, 2_000) } : {}),
      })
      traces.push(`tool:${context.toolCall.name}:${context.isError ? "error" : "ok"}`)
      return undefined
    }

    const timer =
      opts.timeoutMs && opts.timeoutMs > 0
        ? setTimeout(() => agent.abort(), opts.timeoutMs)
        : undefined
    try {
      await agent.prompt(prompt)
    } catch (error) {
      traces.push(`agent:error:${error instanceof Error ? error.message : String(error)}`)
      this.logger.warn(`[pi-task-runner] ${session.record.taskId} turn failed`, error)
    } finally {
      if (timer) clearTimeout(timer)
      session.activeAgent = undefined
    }

    const finalMessages = agent.state.messages
    const paused = pendingStep !== undefined || session.pauseRequested
    const failed = !paused && Boolean(agent.state.errorMessage)
    const status: PiTaskSessionStatus = paused ? "paused" : failed ? "failed" : "idle"
    const reply =
      lastAssistantText(finalMessages) ||
      (pendingStep ? pendingStep.reason : "") ||
      (failed ? (agent.state.errorMessage ?? "任务执行失败") : "")
    const record: PiTaskSessionRecord = {
      ...session.record,
      status,
      snapshot: {
        ...session.record.snapshot,
        messages: cloneMessages(finalMessages),
      },
      pendingStep: pendingStep ?? null,
      updatedAt: nowIso(),
    }
    await this.save(session, record)
    session.running = false

    if (!paused) {
      const goal =
        record.snapshot.summary?.trim() ||
        (opts.approved === undefined ? prompt.trim() : "") ||
        lastUserText(finalMessages) ||
        record.taskId
      await this.recordMemory(record, toolCalls, reply, status, goal)
    }

    const usage = usageOf(finalMessages.slice(beforeCount))
    return {
      taskId: session.record.taskId,
      status,
      reply,
      toolCalls,
      pendingStep: pendingStep ?? null,
      traces,
      usage,
    }
  }
}
