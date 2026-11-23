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
const DEFAULT_APPROVAL_TTL_MS = 30 * 60_000
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
  /** Conversation that owns the task; persisted for approval scoping. */
  readonly conversationId?: string
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
  /** Pending approvals older than this are rejected on resume. `<= 0` disables expiry. */
  readonly approvalTtlMs?: number
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

  async list(): Promise<readonly PiTaskSessionRecord[]> {
    return [...this.records.values()]
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
  /** A turn is waiting for the global lock; a second turn must not queue. */
  queued: boolean
  pauseRequested: boolean
  /** Set by close(); an in-flight turn must not persist after this. */
  closed: boolean
  activeAgent?: Agent
}

interface TurnOptions {
  readonly timeoutMs?: number
  /** undefined = normal turn; true/false = resume a pending approval. */
  readonly approved?: boolean
  readonly approvalNote?: string
}

const SNAPSHOT_VERSION = 1
const MESSAGE_ROLES = new Set(["system", "user", "assistant", "toolResult"])

function nowIso(): string {
  return new Date().toISOString()
}

function cloneMessages(messages: readonly AgentMessage[]): readonly unknown[] {
  return JSON.parse(JSON.stringify(messages)) as unknown[]
}

/**
 * Validate the persisted transcript before it is handed back to the Agent.
 * A corrupted or newer snapshot must fail loudly; silently resetting the
 * session would drop the conversation and re-run side effects.
 */
function parseSnapshot(record: PiTaskSessionRecord): AgentMessage[] {
  const snapshot = record.snapshot
  if (!snapshot || typeof snapshot !== "object") {
    throw new Error(`task ${record.taskId}: session snapshot is missing`)
  }
  if (snapshot.version !== SNAPSHOT_VERSION) {
    throw new Error(
      `task ${record.taskId}: unsupported session snapshot version ${String(snapshot.version)}`,
    )
  }
  if (!Array.isArray(snapshot.messages)) {
    throw new Error(`task ${record.taskId}: session snapshot messages must be an array`)
  }
  const messages = JSON.parse(JSON.stringify(snapshot.messages)) as unknown[]
  let systemCount = 0
  for (const [index, message] of messages.entries()) {
    if (!message || typeof message !== "object") {
      throw new Error(`task ${record.taskId}: invalid message at index ${index}`)
    }
    const role = (message as { role?: unknown }).role
    if (typeof role !== "string" || !MESSAGE_ROLES.has(role)) {
      throw new Error(
        `task ${record.taskId}: invalid message role at index ${index}: ${String(role)}`,
      )
    }
    if (role === "system") systemCount += 1
    if (index === 0 && role !== "system") {
      throw new Error(`task ${record.taskId}: first message must be a system message`)
    }
    if (
      role === "toolResult" &&
      typeof (message as { toolCallId?: unknown }).toolCallId !== "string"
    ) {
      throw new Error(`task ${record.taskId}: tool result at index ${index} has no toolCallId`)
    }
  }
  if (systemCount > 1) {
    throw new Error(`task ${record.taskId}: snapshot contains ${systemCount} system messages`)
  }
  return messages as AgentMessage[]
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
function completeDanglingToolResults(
  messages: readonly AgentMessage[],
  text = "本步未执行。",
): AgentMessage[] {
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
        content: [{ type: "text", text }],
        isError: true,
        timestamp: Date.now(),
      }) satisfies AgentMessage,
  )

  // Results must follow the assistant message that produced the calls. Skip
  // the contiguous results that already belong to this batch and insert the
  // synthetic ones there, never after a later user/assistant message.
  let insertAt = assistantIndex + 1
  while (messages[insertAt]?.role === "toolResult") insertAt += 1
  return [...messages.slice(0, insertAt), ...synthetic, ...messages.slice(insertAt)]
}

export class PiTaskRunner {
  private readonly sessions = new Map<string, SessionState>()
  private readonly store: PiTaskSessionStore
  private readonly policy: PiApprovalPolicy
  private readonly lock: GlobalAgentLock
  private readonly streamFn: StreamFn
  private readonly maxToolCalls: number
  private readonly approvalTtlMs: number
  private readonly logger: { warn(message: string, extra?: unknown): void }

  constructor(private readonly options: PiTaskRunnerOptions) {
    this.store = options.store ?? new MemoryPiTaskSessionStore()
    this.policy = options.approvalPolicy ?? createDefaultApprovalPolicy()
    this.lock = options.lock ?? globalAgentLock
    this.maxToolCalls = options.maxToolCalls ?? DEFAULT_MAX_TOOL_CALLS
    this.approvalTtlMs = options.approvalTtlMs ?? DEFAULT_APPROVAL_TTL_MS
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
        ...(input.conversationId === undefined ? {} : { conversationId: input.conversationId }),
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
      queued: false,
      pauseRequested: false,
      closed: false,
    })
    return record
  }

  async load(taskId: string): Promise<PiTaskSessionRecord | null> {
    const cached = this.sessions.get(taskId)
    if (cached) return cached.record
    const record = await this.store.load(taskId)
    if (record) {
      this.sessions.set(taskId, {
        record,
        running: false,
        queued: false,
        pauseRequested: false,
        closed: false,
      })
    }
    return record
  }

  async start(
    taskId: string,
    prompt: string,
    opts?: { timeoutMs?: number },
  ): Promise<PiTaskTurnResult> {
    const session = await this.requireSession(taskId)
    await this.refresh(session)
    return this.runExclusive(session, () => this.runTurn(session, prompt, opts ?? {}))
  }

  async resume(
    taskId: string,
    decision: { readonly approved: boolean; readonly note?: string },
  ): Promise<PiTaskTurnResult> {
    const session = await this.requireSession(taskId)
    // The store is the source of truth across processes; never act on a cached
    // record that another process may already have advanced.
    await this.refresh(session)
    const pending = session.record.pendingStep
    // Resuming a task that is neither waiting for approval nor paused would
    // inject an approval prompt into a normal turn. Reject before touching any
    // state so the call has no side effects.
    if (pending === null && session.record.status !== "paused") {
      throw new Error(`task ${taskId} is not paused; nothing to resume`)
    }
    if (pending === null) {
      return this.runExclusive(session, () => this.runTurn(session, "继续完成任务。", {}))
    }
    if (pending.decidedAt) {
      return this.settlePendingWithoutRun(
        session,
        pending,
        "该审批已处理，未重复执行。",
        "approval:duplicate",
      )
    }
    if (this.isPendingExpired(pending)) {
      return this.settlePendingWithoutRun(
        session,
        pending,
        "审批已过期，本步未执行。",
        "approval:expired",
      )
    }
    const prompt = decision.approved
      ? "审批已通过，请继续完成任务。"
      : "用户拒绝执行上一步操作，请不要重复该操作，改用其他方式或向用户说明。"
    return this.runExclusive(session, async () => {
      const latest = session.record.pendingStep
      if (latest === null || latest.decidedAt) {
        return this.settleLocked(
          session,
          pending,
          "该审批已处理，未重复执行。",
          "approval:duplicate",
        )
      }
      if (this.isPendingExpired(latest)) {
        return this.settleLocked(session, latest, "审批已过期，本步未执行。", "approval:expired")
      }
      // Claim the decision durably before running the tool. If this process
      // dies mid-execution, another process will not run it a second time.
      await this.save(session, {
        ...session.record,
        pendingStep: { ...latest, decidedAt: nowIso() },
        updatedAt: nowIso(),
      })
      return this.runTurn(session, prompt, {
        approved: decision.approved,
        ...(decision.note === undefined ? {} : { approvalNote: decision.note }),
      })
    })
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
    if (session) {
      session.closed = true
      session.activeAgent?.abort()
    }
    this.sessions.delete(taskId)
    await this.store.delete(taskId)
  }

  list(): readonly PiTaskSessionRecord[] {
    return [...this.sessions.values()].map((session) => session.record)
  }

  /**
   * Every known task: the durable store plus in-memory sessions.
   * In-memory records win because they carry the newest turn.
   */
  async listStored(): Promise<readonly PiTaskSessionRecord[]> {
    const stored = this.store.list ? await this.store.list() : []
    const byId = new Map(stored.map((record) => [record.taskId, record]))
    for (const [taskId, session] of this.sessions) byId.set(taskId, session.record)
    return [...byId.values()]
  }

  private async requireSession(taskId: string): Promise<SessionState> {
    const cached = this.sessions.get(taskId)
    if (cached) return cached
    const record = await this.store.load(taskId)
    if (!record) throw new Error(`task session not found: ${taskId}`)
    const session: SessionState = {
      record,
      running: false,
      queued: false,
      pauseRequested: false,
      closed: false,
    }
    this.sessions.set(taskId, session)
    return session
  }

  /** Replace the cached record with the store's latest version. */
  private async refresh(session: SessionState): Promise<void> {
    const taskId = session.record.taskId
    const fresh = await this.store.load(taskId)
    if (!fresh) {
      this.sessions.delete(taskId)
      throw new Error(`task session not found: ${taskId}`)
    }
    session.record = fresh
  }

  private isPendingExpired(pending: PiTaskPendingStep): boolean {
    if (this.approvalTtlMs <= 0) return false
    const requested = Date.parse(pending.requestedAt)
    if (Number.isNaN(requested)) return true
    return Date.now() - requested > this.approvalTtlMs
  }

  /**
   * Settle a pending step that must not run (duplicate claim or expired TTL):
   * persist an error result for it, clear the pending step, and return a
   * result without starting a model turn.
   */
  private async settleLocked(
    session: SessionState,
    pending: PiTaskPendingStep,
    text: string,
    trace: string,
  ): Promise<PiTaskTurnResult> {
    const messages = completeDanglingToolResults(
      replaceToolResult(parseSnapshot(session.record), pending, text, true),
      "等待审批，本步未执行；批准后请重新发起该调用。",
    )
    const snapshot = {
      ...session.record.snapshot,
      messages: cloneMessages(messages),
      lastReply: text,
    }
    if (snapshot.lastError !== undefined) delete snapshot.lastError
    const record: PiTaskSessionRecord = {
      ...session.record,
      status: "idle",
      snapshot,
      pendingStep: null,
      updatedAt: nowIso(),
    }
    await this.save(session, record)
    return {
      taskId: record.taskId,
      status: "idle",
      reply: text,
      toolCalls: [],
      pendingStep: null,
      traces: [trace],
      usage: { inputTokens: 0, outputTokens: 0, totalTokens: 0 },
    }
  }

  private async settlePendingWithoutRun(
    session: SessionState,
    pending: PiTaskPendingStep,
    text: string,
    trace: string,
  ): Promise<PiTaskTurnResult> {
    return this.runExclusive(session, () => this.settleLocked(session, pending, text, trace))
  }

  /**
   * Serialize turns per task and across tasks. The flags are set before
   * awaiting the global lock, so a second call cannot slip into the gap
   * between the "already running" check and the turn actually starting.
   */
  private async runExclusive<T>(session: SessionState, run: () => Promise<T>): Promise<T> {
    const taskId = session.record.taskId
    if (session.running || session.queued) {
      throw new PiTaskBusyError(taskId, "already running")
    }
    session.queued = true
    try {
      return await this.lock.run(taskId, async () => {
        session.queued = false
        // A task closed while waiting for the lock must not consume the lock
        // or run a turn after the holder finishes.
        if (session.closed) throw new Error(`task ${taskId} was closed`)
        session.running = true
        try {
          return await run()
        } finally {
          session.running = false
        }
      })
    } catch (error) {
      session.queued = false
      throw error
    }
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
    try {
      await this.store.save(record)
    } catch (error) {
      // Surface the task id and the fact that the turn may have executed but
      // was not persisted, instead of a bare driver error.
      throw new Error(
        `task ${record.taskId}: failed to persist session: ${error instanceof Error ? error.message : String(error)}`,
        { cause: error },
      )
    }
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
    session.pauseRequested = false
    // Repair a transcript left with dangling calls by an earlier crash before
    // rebuilding the Agent, so the model never sees an unanswered tool call.
    let messages = completeDanglingToolResults(
      parseSnapshot(session.record),
      "上一次执行被中断，本步未执行。",
    )
    let pending = session.record.pendingStep
    const traces: string[] = []
    const toolCalls: PiTaskToolCall[] = []
    /** Why the turn stopped without a model-authored reply. */
    let terminationReason: string | undefined

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
      messages = completeDanglingToolResults(
        messages,
        "等待审批，本步未执行；批准后请重新发起该调用。",
      )
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
        const reason = `工具调用额度已用尽（上限 ${this.maxToolCalls} 次）`
        terminationReason ??= reason
        return { block: true, terminate: true, reason }
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

    const timeoutMs = opts.timeoutMs
    let timedOut = false
    const timer =
      timeoutMs && timeoutMs > 0
        ? setTimeout(() => {
            timedOut = true
            terminationReason ??= `任务执行超时（${timeoutMs}ms）`
            agent.abort()
          }, timeoutMs)
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

    const pausedByRequest = session.pauseRequested && pendingStep === undefined
    const paused = pendingStep !== undefined || session.pauseRequested
    const failed = !paused && (Boolean(agent.state.errorMessage) || timedOut)
    // close() is final: the record was deleted, so an in-flight turn must not
    // resurrect it with a trailing save.
    const closed = session.closed
    const status: PiTaskSessionStatus = closed
      ? "closed"
      : paused
        ? "paused"
        : failed
          ? "failed"
          : "idle"
    // An aborted batch may leave tool calls without results. Complete them so
    // the persisted transcript is valid and the next turn does not replay them.
    const danglingText =
      pendingStep !== undefined
        ? "等待审批，本步未执行；批准后请重新发起该调用。"
        : pausedByRequest
          ? "任务已暂停，本步未执行。"
          : failed
            ? "任务执行失败，本步未执行。"
            : "本步未执行（任务被中断）。"
    const finalMessages = completeDanglingToolResults(agent.state.messages, danglingText)
    // Reason-bearing endings win over an earlier assistant preamble so the
    // owner never receives an empty or stale reply when the turn was blocked.
    const reply = closed
      ? "任务已关闭。"
      : (pendingStep ? pendingStep.reason : "") ||
        (failed ? (agent.state.errorMessage ?? terminationReason ?? "任务执行失败") : "") ||
        (pausedByRequest ? "任务已暂停。" : "") ||
        (terminationReason ?? "") ||
        lastAssistantText(finalMessages)
    const snapshot: {
      version: 1
      systemPrompt: string
      summary?: string
      messages: readonly unknown[]
      lastReply?: string
      lastError?: string
      conversationId?: string
    } = {
      ...session.record.snapshot,
      messages: cloneMessages(finalMessages),
    }
    if (reply.length > 0) snapshot.lastReply = reply
    if (failed) snapshot.lastError = agent.state.errorMessage ?? reply
    else delete snapshot.lastError
    const record: PiTaskSessionRecord = {
      ...session.record,
      status,
      snapshot,
      pendingStep: pendingStep ?? null,
      updatedAt: nowIso(),
    }
    if (!closed) await this.save(session, record)

    if (!paused && !closed) {
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
