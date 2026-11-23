/**
 * Minimal Butler Runtime.
 *
 * Two channels share one transcript:
 *   - rule channel: deterministic commands answered without a model call;
 *   - agent channel: a small tool loop over the injected model port.
 *
 * The butler never touches the task layer's internals: work is dispatched
 * through `ButlerTaskPort`, and finished sessions are projected through
 * `ButlerMemoryPort` instead of being written to a memory store directly.
 */
import type {
  ButlerMemoryFact,
  ButlerMemoryPort,
  ButlerSessionSummaryEvent,
  RecalledUserMemory,
} from "@butler/ports/core/butler-memory.js"
import type {
  ButlerMessage,
  ButlerSessionRecord,
  ButlerSessionStore,
  ButlerToolCall,
} from "@butler/ports/core/butler-session.js"
import type { ButlerTaskPort, ButlerTaskRef } from "@butler/ports/core/butler-task.js"
import {
  DEFAULT_BUTLER_SYSTEM_PROMPT,
  ZERO_USAGE,
  type ButlerModelPort,
  type ButlerModelReply,
  type ButlerTokenUsage,
  type ButlerToolSpec,
} from "./model-port.js"
import { matchApprovalWord, matchButlerRule, type ButlerRuleAction } from "./rule-router.js"
import { buildApprovalNotice, type ButlerApprovalNotice } from "./approval-notice.js"
import { finalizeReply, taskStatusLabel } from "./presentation.js"
import { MemoryButlerSessionStore } from "./session-store.js"

const DEFAULT_MAX_ITERATIONS = 3
const DEFAULT_MAX_TOOL_CALLS = 8
const DEFAULT_RECALL_LIMIT = 4
const DEFAULT_SUMMARY_EVERY_MESSAGES = 20
const MAX_TRANSCRIPT_CHARS = 6_000
const DEFAULT_WINDOW_TURNS = 12
const DEFAULT_MAX_SUMMARY_CHARS = 2_000
const DEFAULT_MAX_PROMPT_CHARS = 24_000
const DEFAULT_RECALL_CACHE_TTL_MS = 300_000
const MAX_RECALL_CACHE_ENTRIES = 100
/** Questions that cannot be retrieved on their own. */
const REWRITE_HINT = /这个|那个|它|刚才|上面|之前|那次|该|此/

const SUMMARY_PROMPT = [
  "你是管家会话复盘助手。阅读会话记录，只输出 JSON（不要 markdown 代码块）：",
  '{"summary":"一句话概括本次会话","profile":{"displayName":"","communicationStyle":"","preferences":[],"commitments":[]},',
  '"facts":[{"kind":"preference|relationship|commitment|convention|note","title":"","text":""}]}',
  "只保留长期有效、以后仍会用到的信息；一次性任务细节不要写进 facts。",
  "没有把握的字段可以省略或用空字符串。",
].join("\n")

const MEMORY_FACT_KINDS = new Set([
  "preference",
  "relationship",
  "commitment",
  "convention",
  "note",
])

export interface ButlerTurnInput {
  readonly conversationId: string
  readonly userId: string
  readonly projectId?: string
  readonly content: string
  /** Task awaiting approval; enables the 确认 / 拒绝 rules. */
  readonly activeTaskId?: string
}

export interface ButlerTurnResult {
  readonly reply: string
  readonly route: "rule" | "agent"
  readonly rule?: string
  readonly taskId?: string
  readonly traces: readonly string[]
  readonly usage: ButlerTokenUsage
}

export interface ButlerRuntimeOptions {
  readonly model: ButlerModelPort
  readonly tasks?: ButlerTaskPort
  readonly memory?: ButlerMemoryPort
  readonly store?: ButlerSessionStore
  readonly systemPrompt?: string
  readonly maxIterations?: number
  readonly maxToolCalls?: number
  readonly recallLimit?: number
  /** Messages accumulated before an automatic memory projection; 0 disables. */
  readonly summaryEveryMessages?: number
  /** Raw turns kept verbatim; older turns fold into the rolling summary. */
  readonly windowTurns?: number
  readonly maxSummaryChars?: number
  /** Hard cap on transcript chars sent to the model per turn. */
  readonly maxPromptChars?: number
  /** Recall cache TTL; 0 disables caching. */
  readonly recallCacheTtlMs?: number
  /** Normalizes an owner-supplied project name; `null` means unknown. */
  readonly resolveProjectName?: (raw: string) => string | null
  readonly clock?: () => string
  readonly logger?: { warn(message: string, extra?: unknown): void }
}

export interface ButlerSummarizeOptions {
  readonly now?: string
}

interface RuleOutcome {
  readonly reply: string
  readonly taskId?: string
}

export class ButlerRuntime {
  private readonly store: ButlerSessionStore
  private readonly sessions = new Map<string, ButlerSessionRecord>()
  private readonly recallCache = new Map<string, { block: string; expiresAt: string }>()
  private readonly summaryMarks = new Map<string, number>()
  private readonly clock: () => string
  private readonly logger: { warn(message: string, extra?: unknown): void }

  constructor(private readonly options: ButlerRuntimeOptions) {
    this.store = options.store ?? new MemoryButlerSessionStore()
    this.clock = options.clock ?? (() => new Date().toISOString())
    this.logger = options.logger ?? {
      warn: (message, extra) => {
        // eslint-disable-next-line no-console -- operator-facing warning
        console.warn(message, extra ?? "")
      },
    }
  }

  async handle(input: ButlerTurnInput): Promise<ButlerTurnResult> {
    const now = this.clock()
    const loaded = await this.loadSession(input)
    let session = this.compactSession(loaded, now)
    const effectiveProjectId = session.projectId ?? input.projectId
    const traces: string[] = []
    const userMessage: ButlerMessage = { role: "user", content: input.content }
    const rule = matchButlerRule({
      content: input.content,
      ...(input.activeTaskId === undefined ? {} : { activeTaskId: input.activeTaskId }),
    })
    const resolvedRule = rule ?? (await this.resolveApprovalRule(input, effectiveProjectId))

    if (resolvedRule) {
      let outcome: RuleOutcome
      try {
        if (resolvedRule.kind === "project") {
          const switched = this.applyProjectRule(resolvedRule, session, effectiveProjectId)
          session = switched.session
          outcome = { reply: switched.reply }
        } else {
          outcome = await this.applyRule(resolvedRule, input, effectiveProjectId)
        }
      } catch (error) {
        traces.push("rule:error")
        this.logger.warn(`[butler] rule ${resolvedRule.name} failed`, error)
        outcome = { reply: "这个操作暂时没完成，请稍后再试。" }
      }
      const reply = finalizeReply(outcome.reply)
      traces.push(`rule:${resolvedRule.name}`)
      await this.safePersist(
        session,
        [userMessage, { role: "assistant", content: reply }],
        now,
        traces,
      )
      return {
        reply,
        route: "rule",
        rule: resolvedRule.name,
        ...(outcome.taskId === undefined ? {} : { taskId: outcome.taskId }),
        traces,
        usage: ZERO_USAGE,
      }
    }

    return this.finish(await this.runAgent(session, input, userMessage, traces, now))
  }

  /** Single text exit: sanitize, guarantee non-empty, cap length. */
  private finish(result: ButlerTurnResult): ButlerTurnResult {
    return { ...result, reply: finalizeReply(result.reply) }
  }

  /**
   * Projects a finished session into user memory.
   *
   * The model is asked for structured long-term facts; when it returns
   * unusable JSON the runtime falls back to a deterministic summary so memory
   * never silently loses the session.
   */
  async summarize(
    conversationId: string,
    options: ButlerSummarizeOptions = {},
  ): Promise<ButlerSessionSummaryEvent | null> {
    const session = this.sessions.get(conversationId) ?? (await this.store.load(conversationId))
    if (!session) return null
    const transcript = transcriptOf(session)
    if (!transcript) return null

    const occurredAt = options.now ?? this.clock()
    const parsed = await this.extractSummary(transcript)
    const event: ButlerSessionSummaryEvent = {
      userId: session.userId,
      sessionId: session.conversationId,
      summary: parsed.summary,
      ...(parsed.profile === undefined ? {} : { profile: parsed.profile }),
      ...(parsed.facts === undefined ? {} : { facts: parsed.facts }),
      occurredAt,
    }

    if (this.options.memory) {
      try {
        await this.options.memory.recordSessionSummary(event)
      } catch (error) {
        this.logger.warn(`[butler] ${conversationId} memory projection failed`, error)
      }
    }

    await this.store.save({
      ...session,
      summary: event.summary,
      updatedAt: occurredAt,
    })
    if (this.sessions.has(conversationId)) {
      this.sessions.set(conversationId, {
        ...session,
        summary: event.summary,
        updatedAt: occurredAt,
      })
    }
    // Projected memory changed; cached recall blocks are stale.
    this.recallCache.clear()
    return event
  }

  /**
   * Projects the session when enough messages accumulated since the last one.
   * Callers can fire-and-forget: failures are logged and swallowed.
   */
  async summarizeIfDue(conversationId: string): Promise<ButlerSessionSummaryEvent | null> {
    const every = this.options.summaryEveryMessages ?? DEFAULT_SUMMARY_EVERY_MESSAGES
    if (every <= 0) return null
    const session = this.sessions.get(conversationId) ?? (await this.store.load(conversationId))
    if (!session) return null
    const mark = this.summaryMarks.get(conversationId) ?? 0
    if (session.messages.length - mark < every) return null
    this.summaryMarks.set(conversationId, session.messages.length)
    try {
      return await this.summarize(conversationId)
    } catch (error) {
      this.logger.warn(`[butler] ${conversationId} automatic summary failed`, error)
      return null
    }
  }

  async forgetSession(conversationId: string): Promise<void> {
    this.sessions.delete(conversationId)
    this.recallCache.clear()
    await this.store.delete(conversationId)
  }

  /** Notice a transport renders when a task is waiting for approval. */
  async approvalNotice(taskId: string): Promise<ButlerApprovalNotice | null> {
    const tasks = this.options.tasks
    if (!tasks) return null
    const task = await tasks.status(taskId)
    return task ? buildApprovalNotice(task) : null
  }

  /**
   * Card callback entry: the WeChat adapter parses a button payload into
   * `{taskId, approved}` and calls this instead of going through the model.
   */
  async handleApprovalCallback(input: {
    readonly conversationId: string
    readonly userId: string
    readonly taskId: string
    readonly approved: boolean
  }): Promise<ButlerTurnResult> {
    const now = this.clock()
    const loaded = await this.loadSession(input)
    const session = this.compactSession(loaded, now)
    const traces = [`approval-card:${input.approved ? "approve" : "reject"}`]
    const userMessage: ButlerMessage = {
      role: "user",
      content: input.approved ? "确认" : "拒绝",
    }
    const tasks = this.options.tasks
    if (!tasks?.approve) {
      const reply = finalizeReply("任务层尚未接入，暂时无法处理审批。")
      await this.safePersist(
        session,
        [userMessage, { role: "assistant", content: reply }],
        now,
        traces,
      )
      return { reply, route: "rule", rule: "approval-card", traces, usage: ZERO_USAGE }
    }

    const deny = async (message: string): Promise<ButlerTurnResult> => {
      const reply = finalizeReply(message)
      await this.safePersist(
        session,
        [userMessage, { role: "assistant", content: reply }],
        now,
        traces,
      )
      return { reply, route: "rule", rule: "approval-card", traces, usage: ZERO_USAGE }
    }

    let current: ButlerTaskRef | null
    try {
      current = await tasks.status(input.taskId)
    } catch (error) {
      this.logger.warn(`[butler] ${input.conversationId} task lookup failed`, error)
      return deny("任务操作暂时失败，请稍后再试。")
    }
    if (!current) return deny(`没有找到任务 ${input.taskId}。`)
    if (!taskBelongsToConversation(current, input.conversationId, session.projectId)) {
      return deny(`任务 ${input.taskId} 不属于当前会话，无法操作。`)
    }
    if (current.status !== "paused") {
      return deny(`任务 ${input.taskId} 当前不在等待审批（可能已处理）。`)
    }

    let task: ButlerTaskRef | null
    try {
      task = await tasks.approve(input.taskId, input.approved)
    } catch (error) {
      this.logger.warn(`[butler] ${input.conversationId} approval failed`, error)
      return deny("审批暂时没提交成功，请稍后再试。")
    }
    if (!task) return deny(`任务 ${input.taskId} 当前不在等待审批。`)

    const decision = input.approved
      ? `已确认，继续执行 ${task.taskId}。`
      : `已拒绝 ${task.taskId} 的待执行步骤。`
    const detail =
      task.status === "paused"
        ? ""
        : task.error
          ? `\n执行失败：${task.error}`
          : task.lastReply
            ? `\n${task.lastReply}`
            : ""
    // Approving one step can immediately pause on the next one.
    const notice = buildApprovalNotice(task)
    const reply = finalizeReply(
      notice ? `${decision}${detail}\n\n${notice.text}` : `${decision}${detail}`,
    )
    await this.safePersist(
      session,
      [userMessage, { role: "assistant", content: reply }],
      now,
      traces,
    )
    return {
      reply,
      route: "rule",
      rule: "approval-card",
      taskId: task.taskId,
      traces,
      usage: ZERO_USAGE,
    }
  }

  private async loadSession(input: {
    readonly conversationId: string
    readonly userId: string
    readonly projectId?: string
  }): Promise<ButlerSessionRecord> {
    const cached = this.sessions.get(input.conversationId)
    const existing = cached ?? (await this.store.load(input.conversationId))
    if (existing) {
      if (existing.userId !== input.userId) {
        throw new Error(`conversation ${input.conversationId} belongs to another user`)
      }
      // A /project switch is the conversation default and outranks the
      // caller's per-turn hint; the hint only seeds a fresh conversation.
      const projectId = existing.projectId ?? input.projectId
      const merged: ButlerSessionRecord = {
        ...existing,
        ...(projectId === undefined ? {} : { projectId }),
      }
      this.sessions.set(input.conversationId, merged)
      return merged
    }
    const now = this.clock()
    const created: ButlerSessionRecord = {
      conversationId: input.conversationId,
      userId: input.userId,
      ...(input.projectId === undefined ? {} : { projectId: input.projectId }),
      messages: [],
      createdAt: now,
      updatedAt: now,
    }
    this.sessions.set(input.conversationId, created)
    return created
  }

  private async persist(
    session: ButlerSessionRecord,
    messages: readonly ButlerMessage[],
    now: string,
  ): Promise<void> {
    const next: ButlerSessionRecord = {
      ...session,
      messages: [...session.messages, ...messages],
      updatedAt: now,
    }
    this.sessions.set(next.conversationId, next)
    await this.store.save(next)
  }

  /** Resolves a bare "确认/拒绝" to the conversation's single paused task. */
  private async resolveApprovalRule(
    input: ButlerTurnInput,
    projectId?: string,
  ): Promise<ButlerRuleAction | null> {
    const intent = matchApprovalWord(input.content)
    if (!intent) return null
    const tasks = this.options.tasks
    if (!tasks) {
      return { kind: "reply", name: "approve-none", reply: "任务层尚未接入，暂时无法处理审批。" }
    }
    let pending: readonly ButlerTaskRef[]
    try {
      pending = (await tasks.list(projectId ?? input.projectId)).filter(
        (task) => task.status === "paused",
      )
    } catch (error) {
      this.logger.warn(`[butler] ${input.conversationId} pending task lookup failed`, error)
      return {
        kind: "reply",
        name: "approve-error",
        reply: "暂时无法查询待确认任务，请稍后再试。",
      }
    }
    const owned = pending.filter((task) => task.conversationId === input.conversationId)
    const candidates =
      owned.length > 0
        ? owned
        : pending.filter(
            (task) =>
              task.conversationId === undefined &&
              (input.projectId === undefined || task.projectId === input.projectId),
          )
    if (candidates.length === 0) {
      return { kind: "reply", name: "approve-none", reply: "当前没有待确认的任务。" }
    }
    if (candidates.length > 1) {
      return {
        kind: "reply",
        name: "approve-many",
        reply: "有多个待确认的任务，请点击审批卡片，或先用 /status 确认是哪一个。",
      }
    }
    const only = candidates[0]
    if (!only) {
      return { kind: "reply", name: "approve-none", reply: "当前没有待确认的任务。" }
    }
    return {
      kind: "approve",
      name: intent.approved ? "approve" : "reject",
      taskId: only.taskId,
      approved: intent.approved,
    }
  }

  /** Persist best-effort: a store outage must not swallow the reply. */
  private async safePersist(
    session: ButlerSessionRecord,
    messages: readonly ButlerMessage[],
    now: string,
    traces: string[],
  ): Promise<void> {
    try {
      await this.persist(session, messages, now)
    } catch (error) {
      traces.push("store:error")
      this.logger.warn(`[butler] ${session.conversationId} persist failed`, error)
    }
  }

  private applyProjectRule(
    rule: Extract<ButlerRuleAction, { kind: "project" }>,
    session: ButlerSessionRecord,
    current: string | undefined,
  ): { readonly session: ButlerSessionRecord; readonly reply: string } {
    if (rule.projectId === undefined) {
      return {
        session,
        reply:
          current === undefined
            ? "当前还没有选择项目。用 /project <项目ID> 选择。"
            : `当前项目：${current}。用 /project <项目ID> 切换。`,
      }
    }
    const raw = rule.projectId.trim()
    const resolved = this.options.resolveProjectName ? this.options.resolveProjectName(raw) : raw
    if (resolved === null || resolved.length === 0) {
      return {
        session,
        reply: `没有找到项目 ${raw}。用 /project 查看当前项目。`,
      }
    }
    return { session: { ...session, projectId: resolved }, reply: `已切换到项目 ${resolved}。` }
  }

  private async applyRule(
    rule: ButlerRuleAction,
    input: ButlerTurnInput,
    sessionProjectId?: string,
  ): Promise<RuleOutcome> {
    if (rule.kind === "reply") return { reply: rule.reply }

    if (rule.kind === "remember") {
      const memory = this.options.memory
      if (!memory?.rememberUserMemory) {
        return { reply: "当前没有接入长期记忆，这条信息还没有保存。" }
      }
      try {
        await memory.rememberUserMemory({
          userId: input.userId,
          fact: { kind: "note", title: rule.text.slice(0, 30), text: rule.text },
        })
      } catch (error) {
        this.logger.warn(`[butler] remember failed for ${input.userId}`, error)
        return { reply: "保存这条记忆时出错了，请稍后再试。" }
      }
      return { reply: `已记住：${rule.text}` }
    }

    const tasks = this.options.tasks
    if (!tasks) return { reply: "任务层尚未接入，暂时无法处理这个指令。" }
    const projectId = sessionProjectId ?? input.projectId

    switch (rule.kind) {
      case "project": {
        // Handled in `handle` because it mutates the conversation session.
        return { reply: "用 /project 查看或切换项目。" }
      }
      case "list_tasks": {
        const items = await tasks.list(projectId)
        return { reply: formatTaskList(items) }
      }
      case "task_status": {
        const task = await tasks.status(rule.taskId)
        if (!task || !taskVisibleToProject(task, projectId)) {
          return { reply: `没有找到任务 ${rule.taskId}，可以用 /tasks 查看项目任务。` }
        }
        const notice = buildApprovalNotice(task)
        return {
          reply: notice
            ? `任务 ${describeTask(task)}\n\n${notice.text}`
            : `任务 ${describeTask(task)}`,
        }
      }
      case "start_task": {
        if (!projectId) return { reply: "请先选择项目，再创建任务。" }
        const task = await tasks.start({
          projectId,
          goal: rule.goal,
          conversationId: input.conversationId,
        })
        const notice = buildApprovalNotice(task)
        const created = `已创建任务 ${task.taskId}（${task.status}），完成后我会汇总改动。`
        const reply =
          task.status === "failed"
            ? `任务 ${task.taskId} 执行失败：${task.error ?? "未知原因"}`
            : task.lastReply && task.status !== "running" && task.status !== "paused"
              ? `任务 ${task.taskId}（${task.status}）：\n${task.lastReply}`
              : created
        return {
          reply: notice ? `${reply}\n\n${notice.text}` : reply,
          taskId: task.taskId,
        }
      }
      case "approve": {
        if (!tasks.approve) return { reply: "任务层不支持审批转发。" }
        const current = await tasks.status(rule.taskId)
        if (!current) return { reply: `没有找到任务 ${rule.taskId}。` }
        if (
          !taskBelongsToConversation(
            current,
            input.conversationId,
            sessionProjectId ?? input.projectId,
          )
        ) {
          return { reply: `任务 ${rule.taskId} 不属于当前会话，无法操作。` }
        }
        if (current.status !== "paused") {
          return { reply: `任务 ${rule.taskId} 当前不在等待审批（可能已处理）。` }
        }
        const task = await tasks.approve(rule.taskId, rule.approved)
        if (!task) return { reply: `任务 ${rule.taskId} 当前不在等待审批。` }
        const detail =
          task.status === "paused"
            ? ""
            : task.error
              ? `\n执行失败：${task.error}`
              : task.lastReply
                ? `\n${task.lastReply}`
                : ""
        return {
          reply: rule.approved
            ? `已确认，继续执行 ${task.taskId}。${detail}`
            : `已拒绝 ${task.taskId} 的待执行步骤。${detail}`,
          taskId: task.taskId,
        }
      }
    }
  }

  private async runAgent(
    session: ButlerSessionRecord,
    input: ButlerTurnInput,
    userMessage: ButlerMessage,
    traces: string[],
    now: string,
  ): Promise<ButlerTurnResult> {
    const memoryBlock = await this.recallBlock(session, input.content, traces)
    const projectId = session.projectId ?? input.projectId
    const bounded = this.enforcePromptBudget(session, memoryBlock, input.content, now)
    const summaryBlock = bounded.summary ? `\n\n[此前对话摘要]\n${bounded.summary}` : ""
    const messages: ButlerMessage[] = [
      {
        role: "system",
        content: `${this.options.systemPrompt ?? DEFAULT_BUTLER_SYSTEM_PROMPT}${memoryBlock}${summaryBlock}`,
      },
      ...bounded.messages.filter((message) => message.role !== "system"),
      userMessage,
    ]
    const toolSpecs = this.toolSpecs()
    const maxIterations = this.options.maxIterations ?? DEFAULT_MAX_ITERATIONS
    const maxToolCalls = this.options.maxToolCalls ?? DEFAULT_MAX_TOOL_CALLS
    let usage = ZERO_USAGE
    let executed = 0
    let reply = ""
    let taskId: string | undefined

    for (let iteration = 0; iteration < maxIterations; iteration += 1) {
      traces.push(`agent:iteration:${iteration + 1}`)
      let completion: ButlerModelReply
      try {
        completion = await this.options.model.complete({
          messages,
          ...(toolSpecs.length > 0 ? { tools: toolSpecs } : {}),
        })
      } catch (error) {
        traces.push(`agent:error:${error instanceof Error ? error.message : String(error)}`)
        this.logger.warn(`[butler] ${input.conversationId} model call failed`, error)
        reply = "管家暂时无法处理这条消息，请稍后再试。"
        break
      }
      usage = addUsage(usage, completion.usage)
      traces.push(`agent:reply:${completion.toolCalls?.length ? "tools" : "text"}`)

      if (!completion.toolCalls || completion.toolCalls.length === 0) {
        reply = completion.content.trim() || "我先记下了，需要我继续处理时告诉我。"
        break
      }

      messages.push({
        role: "assistant",
        content: completion.content,
        toolCalls: completion.toolCalls,
      })
      for (const call of completion.toolCalls) {
        if (executed >= maxToolCalls) {
          messages.push({
            role: "tool",
            content: "工具调用预算已用完，请直接给出结论。",
            toolCallId: call.id,
            toolName: call.name,
          })
          traces.push(`tool:${call.name}:budget`)
          continue
        }
        executed += 1
        const outcome = await this.executeTool(call, input, projectId)
        traces.push(`tool:${call.name}:${outcome.failed ? "error" : "ok"}`)
        if (outcome.taskId) taskId = outcome.taskId
        messages.push({
          role: "tool",
          content: outcome.output,
          toolCallId: call.id,
          toolName: call.name,
        })
      }
    }

    if (!reply) {
      reply = "这轮处理步骤较多，我先停在这里。你可以继续追问或让我重试。"
      traces.push("agent:iteration-limit")
    }

    await this.safePersist(
      bounded,
      [userMessage, { role: "assistant", content: reply }],
      now,
      traces,
    )
    return {
      reply,
      route: "agent",
      ...(taskId === undefined ? {} : { taskId }),
      traces,
      usage,
    }
  }

  private toolSpecs(): readonly ButlerToolSpec[] {
    if (!this.options.tasks) return []
    return [
      {
        name: "start_task",
        description: "把编码任务交给任务层执行。目标需要具体、可验证。",
        parameters: {
          type: "object",
          properties: {
            goal: { type: "string", description: "任务目标" },
          },
          required: ["goal"],
        },
      },
      {
        name: "list_tasks",
        description: "列出当前项目的任务及状态。",
        parameters: { type: "object", properties: {} },
      },
      {
        name: "task_status",
        description: "查询单个任务的状态。",
        parameters: {
          type: "object",
          properties: {
            taskId: { type: "string", description: "任务 ID" },
          },
          required: ["taskId"],
        },
      },
    ]
  }

  private async executeTool(
    call: ButlerToolCall,
    input: ButlerTurnInput,
    sessionProjectId?: string,
  ): Promise<{ output: string; taskId?: string; failed?: boolean }> {
    const tasks = this.options.tasks
    if (!tasks) return { output: "任务层尚未接入。", failed: true }
    const projectId = sessionProjectId ?? input.projectId
    try {
      switch (call.name) {
        case "start_task": {
          const goal = asNonEmptyString(call.args["goal"])
          if (!goal) return { output: "缺少任务目标。", failed: true }
          if (!projectId) {
            return { output: "当前会话未绑定项目，无法创建任务。", failed: true }
          }
          const task = await tasks.start({
            projectId,
            goal,
            conversationId: input.conversationId,
          })
          const output =
            task.status === "failed"
              ? `任务 ${task.taskId} 执行失败：${task.error ?? "未知原因"}`
              : task.lastReply && task.status !== "running" && task.status !== "paused"
                ? `任务 ${task.taskId}（${task.status}）：\n${task.lastReply}`
                : `已创建任务 ${task.taskId}（${task.status}）。`
          return { output, taskId: task.taskId }
        }
        case "list_tasks": {
          const items = await tasks.list(projectId)
          return { output: formatTaskList(items) }
        }
        case "task_status": {
          const taskId = asNonEmptyString(call.args["taskId"]) ?? input.activeTaskId
          if (!taskId) return { output: "缺少任务 ID。", failed: true }
          const task = await tasks.status(taskId)
          if (!task || !taskVisibleToProject(task, projectId)) {
            return { output: `没有找到任务 ${taskId}。`, failed: true }
          }
          return { output: describeTask(task) }
        }
        default:
          return { output: `未知工具：${call.name}`, failed: true }
      }
    } catch (error) {
      this.logger.warn(`[butler] tool ${call.name} failed`, error)
      return {
        output: `工具执行失败：${error instanceof Error ? error.message : String(error)}`,
        failed: true,
      }
    }
  }

  private async recallBlock(
    session: ButlerSessionRecord,
    query: string,
    traces: string[],
  ): Promise<string> {
    const memory = this.options.memory
    if (!memory?.recallUserMemory) return ""
    const limit = this.options.recallLimit ?? DEFAULT_RECALL_LIMIT
    const cacheKey = `${session.userId}|${limit}|${query.trim()}`
    const cached = this.readRecallCache(cacheKey)
    if (cached !== undefined) {
      traces.push("memory:recall:cache")
      return cached.block
    }

    let hits = await this.safeRecall(query, limit, traces, session.userId)
    if (hits.length === 0 && this.shouldRewrite(query, session)) {
      const rewritten = await this.rewriteQuery(session, query, traces)
      if (rewritten !== null) {
        traces.push("memory:rewrite")
        hits = await this.safeRecall(rewritten, limit, traces, session.userId)
        if (hits.length === 0) {
          // 改写仍空时退回最近有效记忆，避免整轮丢掉画像。
          hits = await this.safeRecall("", limit, traces, session.userId)
          if (hits.length > 0) traces.push("memory:recall:fallback")
        }
      }
    }

    const block =
      hits.length === 0
        ? ""
        : `\n\n已知用户信息（来自长期记忆，仅供参考）：\n${hits
            .map((hit) => `- ${hit.title}：${hit.text}`)
            .join("\n")}`
    this.writeRecallCache(cacheKey, block)
    return block
  }

  private async safeRecall(
    query: string,
    limit: number,
    traces: string[],
    userId: string,
  ): Promise<readonly RecalledUserMemory[]> {
    const recall = this.options.memory?.recallUserMemory
    if (!recall) return []
    try {
      const hits = await recall(query, limit, userId)
      traces.push(`memory:recall:${hits.length}`)
      return hits
    } catch (error) {
      traces.push("memory:recall:error")
      this.logger.warn("[butler] memory recall failed", error)
      return []
    }
  }

  private readRecallCache(key: string): { block: string } | undefined {
    const ttl = this.options.recallCacheTtlMs ?? DEFAULT_RECALL_CACHE_TTL_MS
    if (ttl <= 0) return undefined
    const entry = this.recallCache.get(key)
    if (!entry) return undefined
    if (Date.parse(entry.expiresAt) <= Date.parse(this.clock())) {
      this.recallCache.delete(key)
      return undefined
    }
    return { block: entry.block }
  }

  private writeRecallCache(key: string, block: string): void {
    const ttl = this.options.recallCacheTtlMs ?? DEFAULT_RECALL_CACHE_TTL_MS
    if (ttl <= 0) return
    if (this.recallCache.size >= MAX_RECALL_CACHE_ENTRIES) {
      const oldest = this.recallCache.keys().next()
      if (!oldest.done) this.recallCache.delete(oldest.value)
    }
    this.recallCache.set(key, {
      block,
      expiresAt: new Date(Date.parse(this.clock()) + ttl).toISOString(),
    })
  }

  /** Ambiguous follow-ups cannot be retrieved without rewriting. */
  private shouldRewrite(query: string, session: ButlerSessionRecord): boolean {
    const trimmed = query.trim()
    if (trimmed.length === 0) return false
    if (session.messages.length === 0) return false
    return trimmed.length <= 8 || REWRITE_HINT.test(trimmed)
  }

  private async rewriteQuery(
    session: ButlerSessionRecord,
    query: string,
    traces: string[],
  ): Promise<string | null> {
    const history = session.messages
      .filter((message) => message.role !== "system")
      .slice(-6)
      .map((message) => `${roleLabel(message.role)}：${clip(message.content, 160)}`)
      .join("\n")
    try {
      const completion = await this.options.model.complete({
        messages: [
          {
            role: "system",
            content:
              "把当前问题改写成一个不依赖上下文、可直接检索的短句。只输出改写后的查询，不要解释，不要引号。",
          },
          { role: "user", content: `最近对话：\n${history}\n\n当前问题：${query}` },
        ],
      })
      const rewritten = completion.content
        .trim()
        .replace(/^["'「『]|["'」』]$/g, "")
        .slice(0, 120)
      return rewritten.length > 0 ? rewritten : null
    } catch (error) {
      traces.push("memory:rewrite:error")
      this.logger.warn("[butler] query rewrite failed", error)
      return null
    }
  }

  private compactSession(session: ButlerSessionRecord, now: string): ButlerSessionRecord {
    // Keep window-1 prior turns so that after this turn is persisted the
    // transcript still holds exactly `windowTurns` turns.
    const keepPrev = Math.max(1, this.options.windowTurns ?? DEFAULT_WINDOW_TURNS) - 1
    const turns = splitTurns(session.messages)
    if (turns.length <= keepPrev) return session
    const overflow = turns.slice(0, turns.length - keepPrev)
    let summary = session.summary
    for (const turn of overflow) summary = this.mergeSummary(summary, turn)
    const kept = keepPrev === 0 ? [] : turns.slice(-keepPrev).flat()
    return {
      ...session,
      messages: kept,
      ...(summary === undefined ? {} : { summary }),
      updatedAt: now,
    }
  }

  /** Folds the oldest turns into the summary until the prompt fits. */
  private enforcePromptBudget(
    session: ButlerSessionRecord,
    memoryBlock: string,
    current: string,
    now: string,
  ): ButlerSessionRecord {
    const max = this.options.maxPromptChars ?? DEFAULT_MAX_PROMPT_CHARS
    const base =
      (this.options.systemPrompt ?? DEFAULT_BUTLER_SYSTEM_PROMPT).length + memoryBlock.length
    let turns = splitTurns(session.messages)
    let summary = session.summary
    let size = turns.reduce((total, turn) => total + turnChars(turn), 0)
    let changed = false
    while (size + base + current.length + (summary?.length ?? 0) > max && turns.length > 1) {
      const oldest = turns[0]
      if (!oldest) break
      summary = this.mergeSummary(summary, oldest)
      size -= turnChars(oldest)
      turns = turns.slice(1)
      changed = true
    }
    if (!changed) return session
    return {
      ...session,
      messages: turns.flat(),
      ...(summary === undefined ? {} : { summary }),
      updatedAt: now,
    }
  }

  private mergeSummary(
    summary: string | undefined,
    turn: readonly ButlerMessage[],
  ): string | undefined {
    const digest = turnDigest(turn)
    if (digest.length === 0) return summary
    const merged = summary === undefined || summary.length === 0 ? digest : `${summary}\n${digest}`
    return truncateTail(merged, this.options.maxSummaryChars ?? DEFAULT_MAX_SUMMARY_CHARS)
  }

  private async extractSummary(transcript: string): Promise<{
    summary: string
    profile?: ButlerSessionSummaryEvent["profile"]
    facts?: readonly ButlerMemoryFact[]
  }> {
    const fallback = transcriptFallback(transcript)
    let raw = ""
    try {
      const completion = await this.options.model.complete({
        messages: [
          { role: "system", content: SUMMARY_PROMPT },
          { role: "user", content: transcript },
        ],
      })
      raw = completion.content
    } catch (error) {
      this.logger.warn("[butler] summary model call failed", error)
      return { summary: fallback }
    }

    const parsed = firstJsonObject(raw)
    if (!parsed) return { summary: fallback }
    const summary = asNonEmptyString(parsed["summary"]) ?? fallback
    const profile = normalizeProfile(parsed["profile"])
    const facts = normalizeFacts(parsed["facts"])
    return {
      summary,
      ...(profile === undefined ? {} : { profile }),
      ...(facts === undefined ? {} : { facts }),
    }
  }
}

function roleLabel(role: ButlerMessage["role"]): string {
  switch (role) {
    case "user":
      return "用户"
    case "assistant":
      return "助手"
    case "tool":
      return "工具"
    default:
      return "系统"
  }
}

/** One turn = a user message plus the assistant/tool messages it produced. */
function splitTurns(messages: readonly ButlerMessage[]): ButlerMessage[][] {
  const turns: ButlerMessage[][] = []
  for (const message of messages) {
    const current = turns[turns.length - 1]
    if (message.role === "user" || current === undefined) {
      turns.push([message])
    } else {
      current.push(message)
    }
  }
  return turns
}

function turnChars(turn: readonly ButlerMessage[]): number {
  return turn.reduce((total, message) => total + message.content.length, 0)
}

function turnDigest(turn: readonly ButlerMessage[]): string {
  const user = turn.find((message) => message.role === "user")?.content ?? ""
  const assistant = turn
    .filter((message) => message.role === "assistant")
    .map((message) => message.content.trim())
    .filter((text) => text.length > 0)
    .join(" ")
  const parts: string[] = []
  if (user.trim().length > 0) parts.push(`用户：${clip(user, 120)}`)
  if (assistant.length > 0) parts.push(`助手：${clip(assistant, 180)}`)
  return parts.join("｜")
}

function clip(text: string, max: number): string {
  const trimmed = text.trim()
  return trimmed.length <= max ? trimmed : `${trimmed.slice(0, max)}…`
}

/** Keeps the newest part of a rolling summary. */
function truncateTail(text: string, max: number): string {
  return text.length <= max ? text : `…${text.slice(text.length - max)}`
}

function asNonEmptyString(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined
  const trimmed = value.trim()
  return trimmed ? trimmed : undefined
}

function asStringList(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined
  const items = value
    .map((item) => asNonEmptyString(item))
    .filter((item): item is string => item !== undefined)
  return items.length > 0 ? items : undefined
}

function normalizeProfile(value: unknown): ButlerSessionSummaryEvent["profile"] | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined
  const raw = value as Record<string, unknown>
  const displayName = asNonEmptyString(raw["displayName"])
  const communicationStyle = asNonEmptyString(raw["communicationStyle"])
  const preferences = asStringList(raw["preferences"])
  const commitments = asStringList(raw["commitments"])
  const profile: NonNullable<ButlerSessionSummaryEvent["profile"]> = {
    ...(displayName === undefined ? {} : { displayName }),
    ...(communicationStyle === undefined ? {} : { communicationStyle }),
    ...(preferences === undefined ? {} : { preferences }),
    ...(commitments === undefined ? {} : { commitments }),
  }
  return Object.keys(profile).length > 0 ? profile : undefined
}

function normalizeFacts(value: unknown): readonly ButlerMemoryFact[] | undefined {
  if (!Array.isArray(value)) return undefined
  const facts: ButlerMemoryFact[] = []
  for (const item of value) {
    if (!item || typeof item !== "object" || Array.isArray(item)) continue
    const raw = item as Record<string, unknown>
    const title = asNonEmptyString(raw["title"])
    const text = asNonEmptyString(raw["text"])
    if (!title || !text) continue
    const kind = asNonEmptyString(raw["kind"])
    const tags = asStringList(raw["tags"])
    facts.push({
      title,
      text,
      ...(kind && MEMORY_FACT_KINDS.has(kind) ? { kind: kind as ButlerMemoryFact["kind"] } : {}),
      ...(tags === undefined ? {} : { tags }),
    })
  }
  return facts.length > 0 ? facts : undefined
}

/** Extract the first balanced `{...}` block so prose around JSON is tolerated. */
function firstJsonObject(raw: string): Record<string, unknown> | null {
  const start = raw.indexOf("{")
  if (start < 0) return null
  let depth = 0
  let inString = false
  let escaped = false
  for (let index = start; index < raw.length; index += 1) {
    const char = raw[index]
    if (inString) {
      if (escaped) escaped = false
      else if (char === "\\") escaped = true
      else if (char === '"') inString = false
      continue
    }
    if (char === '"') {
      inString = true
      continue
    }
    if (char === "{") depth += 1
    else if (char === "}") {
      depth -= 1
      if (depth === 0) {
        try {
          const parsed = JSON.parse(raw.slice(start, index + 1)) as unknown
          return parsed && typeof parsed === "object" && !Array.isArray(parsed)
            ? (parsed as Record<string, unknown>)
            : null
        } catch {
          return null
        }
      }
    }
  }
  return null
}

function transcriptOf(session: ButlerSessionRecord): string {
  const lines: string[] = []
  for (const message of session.messages) {
    if (message.role !== "user" && message.role !== "assistant") continue
    const content = message.content.trim()
    if (!content) continue
    lines.push(`${message.role === "user" ? "用户" : "管家"}：${content}`)
  }
  const transcript = lines.join("\n")
  return transcript.length > MAX_TRANSCRIPT_CHARS
    ? transcript.slice(transcript.length - MAX_TRANSCRIPT_CHARS)
    : transcript
}

function transcriptFallback(transcript: string): string {
  const last = transcript.split("\n").filter(Boolean).pop()
  const fallback = last ? last.replace(/^(?:用户|管家)：/, "") : "本次会话没有形成有效结论。"
  return fallback.length > 200 ? `${fallback.slice(0, 200)}…` : fallback
}

function taskVisibleToProject(task: ButlerTaskRef, projectId: string | undefined): boolean {
  return projectId === undefined || task.projectId === projectId
}

function taskBelongsToConversation(
  task: ButlerTaskRef,
  conversationId: string,
  projectId: string | undefined,
): boolean {
  if (task.conversationId !== undefined) return task.conversationId === conversationId
  // Tasks created before conversation binding fall back to project scope.
  return projectId === undefined || task.projectId === projectId
}

function describeTask(task: ButlerTaskRef): string {
  const suffix = task.summary ? `：${task.summary}` : ""
  const result =
    task.status === "paused"
      ? ""
      : task.error
        ? `\n失败原因：${task.error}`
        : task.lastReply
          ? `\n结果：${task.lastReply}`
          : ""
  return `${task.taskId}（${taskStatusLabel(task.status)}${suffix}）${result}`
}

function formatTaskList(items: readonly ButlerTaskRef[]): string {
  if (items.length === 0) return "当前没有任务。"
  return `共 ${items.length} 个任务：\n${items.map((item) => `- ${describeTask(item)}`).join("\n")}`
}

function addUsage(base: ButlerTokenUsage, extra: ButlerTokenUsage | undefined): ButlerTokenUsage {
  if (!extra) return base
  return {
    inputTokens: base.inputTokens + extra.inputTokens,
    outputTokens: base.outputTokens + extra.outputTokens,
    totalTokens: base.totalTokens + extra.totalTokens,
  }
}
