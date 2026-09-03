import type { EventBridge } from "@butler/persistence/event-bridge.js"
import type { RuntimeStore, StoredMessage } from "@butler/domain/runtime.js"
import type { DurableMemoryStore, DocumentStore, ProjectKnowledgeStore } from "@butler/persistence"
import { resolveReadModelSource } from "@butler/domain/runtime.js"
import type { LLMTool } from "@butler/adapters"
import {
  ALLOWED_CAPABILITIES,
  delegate,
  type Capability,
} from "@butler/runtime/delegate-runtime.js"
import type { RunResult, ToolDefinition } from "@butler/runtime/tool-runtime.js"
import { writeSubagentAudit } from "./audit-service.js"
import { recordChildRunDelegated } from "./project-state.js"
import { makeSendWechatFileTool } from "./send-wechat-file.js"
import {
  makeReadFileTool,
  makeRunCommandTool,
  makeWriteFileTool,
  type WorkspaceToolContext,
} from "./workspace-tools.js"
import { loadMcpToolDefinitions, loadMcpLlmTools, type McpToolsOptions } from "./mcp-tools.js"
import type { McpToolBundle } from "./mcp-bootstrap.js"
import { isSubagentEnabled } from "./subagent-config.js"
import { defaultCapabilitiesForRole } from "./delegate-capabilities.js"

/**
 * Minimal context passed to tool handlers. The butler loop wires the
 * current EventBridge + conversation id so tools like `recall_history`
 * can read the configured read model (0002 messages by default, with
 * event_store fallback) without taking a global dependency.
 *
 * `actor` (R8.x.6) is the typed actor that will be recorded on any
 * domain events the tool emits (e.g. ChildRunCreated). Tools that do
 * not emit events can leave it undefined.
 */
export interface ButlerToolContext {
  readonly bridge: EventBridge
  readonly conversationId: string
  readonly actor?: { readonly kind: "owner" | "agent" | "system"; readonly id: string }
  readonly runtimeStore?: RuntimeStore
  /** Parent Run id for Child Run creation on delegate (A5). */
  readonly runId?: string
  /**
   * D5-arch-align §20 #5: tools the parent Run is currently permitted to invoke.
   * Used to enforce that any child Run delegated from this parent does not
   * grant capabilities outside the parent's allowlist. Optional; if absent,
   * the delegate tool cannot enforce subset (no parent knowledge available).
   */
  readonly parentAllowedToolNames?: readonly string[]
  /** Sandbox root for read_file / write_file / run_command. Defaults to cwd / env. */
  readonly workspaceRoot?: string
  /** Current inbound WeChat user; required by send_wechat_file. */
  readonly wechatUserId?: string
  readonly wechatContextToken?: string
  readonly env?: NodeJS.ProcessEnv
  /** Inject MCP discovery/invoke for tests; production uses wiring.mcp from bootstrap. */
  readonly mcp?: McpToolsOptions
  readonly mcpBundle?: McpToolBundle
  /** Durable Memory store for explicit recall (layer 2 knowledge). */
  readonly durableMemoryStore?: DurableMemoryStore | null
  /** Document ingest store for explicit recall. */
  readonly documentStore?: DocumentStore | null
  /** Subject whose memories to search (usually owner / wechat user). */
  readonly memorySubject?: string
  /** Conversation project id for project-scoped recall. */
  readonly projectId?: string
  /** Project Knowledge store for explicit recall. */
  readonly projectKnowledgeStore?: ProjectKnowledgeStore | null
}

function storedMessageText(content: Readonly<Record<string, unknown>>): string {
  const text = content["text"]
  if (typeof text === "string") return text
  const body = content["body"]
  if (typeof body === "string") return body
  return JSON.stringify(content)
}

type ToolHistory =
  | { readonly kind: "messages"; readonly rows: readonly StoredMessage[] }
  | {
      readonly kind: "events"
      readonly rows: Awaited<ReturnType<EventBridge["loadStream"]>>
    }

/**
 * Prefer 0002 `messages` when BUTLER_V5_READ_MODEL is hybrid/relational
 * and RuntimeStore is wired; otherwise fall back to event_store.
 */
export async function loadToolConversationHistory(ctx: ButlerToolContext): Promise<ToolHistory> {
  const source = resolveReadModelSource(ctx.env ?? process.env)
  if (source !== "event_store" && ctx.runtimeStore) {
    const messages = await ctx.runtimeStore.listMessages(ctx.conversationId)
    if (source === "relational" || messages.length > 0) {
      return { kind: "messages", rows: messages }
    }
  }
  return { kind: "events", rows: await ctx.bridge.loadStream(ctx.conversationId) }
}

/**
 * Build a tool whose `run` catches any throw and maps it to the
 * `{ ok: false, reason }` envelope. Removes the repeated try/catch +
 * envelope boilerplate from each tool handler; behavior-preserving.
 */
function makeTool(
  name: string,
  risk: ToolDefinition["risk"],
  run: (args: Record<string, unknown>) => Promise<RunResult>,
): ToolDefinition {
  return {
    name: name as ToolDefinition["name"],
    risk,
    async run(args: Record<string, unknown>): Promise<RunResult> {
      try {
        return await run(args)
      } catch (err) {
        return { ok: false, reason: err instanceof Error ? err.message : String(err) }
      }
    },
  }
}

/**
 * `recall_history` — recall recent conversation turns from the configured
 * read model (0002 messages by default). Marked low-risk: it only reads.
 */
export function makeRecallHistoryTool(ctx: ButlerToolContext): ToolDefinition {
  return makeTool("recall_history", "low", async (args) => {
    const limitRaw = args["limit"]
    const limit =
      typeof limitRaw === "number" && Number.isFinite(limitRaw) && limitRaw > 0
        ? Math.min(Math.floor(limitRaw), 20)
        : 5
    const history = await loadToolConversationHistory(ctx)
    if (history.kind === "messages") {
      const recent = history.rows.slice(-limit)
      const lines = recent.map((m, i) => `${i + 1}. [${m.role}] ${storedMessageText(m.content)}`)
      return {
        ok: true,
        output: lines.length > 0 ? lines.join("\n") : "(no prior events)",
      }
    }
    const recent = history.rows.slice(-limit)
    const lines = recent.map((e, i) => {
      const payload = e.payload as Record<string, unknown>
      const content = typeof payload["content"] === "string" ? (payload["content"] as string) : ""
      return `${i + 1}. [${e.eventType}] ${content}`
    })
    return {
      ok: true,
      output: lines.length > 0 ? lines.join("\n") : "(no prior events)",
    }
  })
}

/**
 * R8.x.5: the wechat butler is for Chinese-language users in China.
 * The current time is always presented in Asia/Shanghai (UTC+8) so the
 * model can quote it back verbatim without the user having to reconcile
 * a UTC label.
 */
const SHANGHAI_TIMEZONE = "Asia/Shanghai" as const
const SHANGHAI_UTC_OFFSET = "UTC+8" as const

/**
 * `get_current_time` — R8.x.5: return the wall-clock time formatted in
 * Asia/Shanghai (UTC+8) with Chinese date + weekday labels. The label
 * is included so the model can quote it without converting between
 * zones. Marked low-risk: pure read, no side effects.
 */
export function makeGetCurrentTimeTool(): ToolDefinition {
  return makeTool("get_current_time", "low", async () => {
    const formatted = new Intl.DateTimeFormat("zh-CN", {
      timeZone: SHANGHAI_TIMEZONE,
      year: "numeric",
      month: "long",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
      weekday: "long",
    }).format(new Date())
    return {
      ok: true,
      output: `当前时区: ${SHANGHAI_TIMEZONE} (${SHANGHAI_UTC_OFFSET})\n${formatted}`,
    }
  })
}

/**
 * `greet_with_time` — return a Chinese greeting based on the local
 * hour in Asia/Shanghai. Lets the model greet the user naturally
 * (早晨好 / 上午好 / 中午好 / 下午好 / 晚上好 / 夜深了) without having
 * to map an hour to a greeting inline. Marked low-risk: pure read.
 */
export function makeGreetWithTimeTool(): ToolDefinition {
  return makeTool("greet_with_time", "low", async () => {
    const hourRaw = new Intl.DateTimeFormat("en-US", {
      timeZone: SHANGHAI_TIMEZONE,
      hour: "numeric",
      hour12: false,
    }).format(new Date())
    const hour = Number.parseInt(hourRaw, 10)
    const safeHour = Number.isFinite(hour) ? hour : 0
    const greeting = pickGreeting(safeHour)
    return { ok: true, output: greeting }
  })
}

/**
 * Map an Asia/Shanghai hour (0-23) to a Chinese greeting. The bucket
 * boundaries match the conventional Chinese time-of-day labels and
 * are intentionally exported only as a return value — the LLM should
 * quote the result verbatim rather than re-deriving the hour.
 */
function pickGreeting(hour: number): string {
  if (hour >= 5 && hour < 9) return "早晨好"
  if (hour >= 9 && hour < 12) return "上午好"
  if (hour >= 12 && hour < 14) return "中午好"
  if (hour >= 14 && hour < 18) return "下午好"
  if (hour >= 18 && hour < 23) return "晚上好"
  return "夜深了"
}

/**
 * `summarize_today` — summarize the last 24 hours from the configured
 * read model (0002 messages by default; event_store fallback). Marked
 * low-risk: pure read. Errors return an envelope rather than throwing.
 */
export function makeSummarizeTodayTool(ctx: ButlerToolContext): ToolDefinition {
  return makeTool("summarize_today", "low", async () => {
    const history = await loadToolConversationHistory(ctx)
    const cutoff = Date.now() - 24 * 60 * 60 * 1000
    if (history.kind === "messages") {
      const recent = history.rows.filter((m) => m.createdAt.getTime() >= cutoff)
      const counts = new Map<string, number>()
      for (const m of recent) {
        counts.set(m.role, (counts.get(m.role) ?? 0) + 1)
      }
      const breakdown = Array.from(counts.entries())
        .sort((a, b) => b[1] - a[1])
        .map(([role, count]) => `${role}: ${count}`)
        .join(", ")
      const summary =
        recent.length === 0
          ? "过去 24 小时内没有消息记录。"
          : `过去 24 小时共 ${recent.length} 条消息。\n按角色: ${breakdown}`
      return { ok: true, output: summary }
    }
    const recent = history.rows.filter((e) => {
      const ts = e.occurredAt instanceof Date ? e.occurredAt.getTime() : 0
      return ts >= cutoff
    })
    const counts = new Map<string, number>()
    for (const e of recent) {
      counts.set(e.eventType, (counts.get(e.eventType) ?? 0) + 1)
    }
    const breakdown = Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([type, count]) => `${type}: ${count}`)
      .join(", ")
    const summary =
      recent.length === 0
        ? "过去 24 小时内没有事件记录。"
        : `过去 24 小时共 ${recent.length} 条事件。\n按类型: ${breakdown}`
    return { ok: true, output: summary }
  })
}

/**
 * `delegate_to_subagent` — R8.x.6: hand off a task to a child agent via
 * the v5 delegate-runtime. The child runs asynchronously (outbox +
 * worker) and reports back through its own conversation stream; this
 * tool returns immediately with the new childConversationId so the
 * parent butler loop can keep iterating or finish. Marked medium-risk:
 * it spawns a child run (writes ChildRunCreated + outbox message).
 *
 * R8.x.9: capabilities arg (optional) must come from
 * `ALLOWED_CAPABILITIES`. Defaults to `["general"]` if unspecified.
 */
export function makeDelegateToSubagentTool(ctx: ButlerToolContext): ToolDefinition {
  const defaultActor: { readonly kind: "agent" | "system" | "owner"; readonly id: string } = {
    kind: "agent",
    id: "wechat-butler-v5",
  }
  return makeTool("delegate_to_subagent", "medium", async (args) => {
    const taskRaw = args["task"]
    const roleRaw = args["role"]
    const capsRaw = args["capabilities"]
    const task = typeof taskRaw === "string" ? taskRaw.trim() : ""
    if (!task) return { ok: false, reason: "task is required" }
    const role = typeof roleRaw === "string" && roleRaw.trim() ? roleRaw.trim() : "general"
    const requestedCaps: readonly string[] = Array.isArray(capsRaw)
      ? capsRaw.filter((c): c is string => typeof c === "string")
      : []
    const effectiveCaps =
      requestedCaps.length > 0 ? requestedCaps : defaultCapabilitiesForRole(role)
    const allowedSet = new Set<string>(ALLOWED_CAPABILITIES)
    const invalid = effectiveCaps.find((c) => !allowedSet.has(c))
    if (invalid !== undefined) {
      writeSubagentAudit(ctx.runtimeStore, {
        ts: new Date().toISOString(),
        kind: "rejection",
        parentConversationId: ctx.conversationId,
        childConversationId: "",
        role,
        task,
        capabilities: effectiveCaps,
        reason: `invalid capability: ${invalid} (allowed: ${ALLOWED_CAPABILITIES.join(", ")})`,
      })
      return {
        ok: false,
        reason: `invalid capability: ${invalid} (allowed: ${ALLOWED_CAPABILITIES.join(", ")})`,
      }
    }
    // Branding via ToolDefinition["name"] keeps us type-compatible
    // with Capability["tool"] without re-deriving the branded
    // string elsewhere.
    const capabilities: Capability[] = effectiveCaps.map(
      (c) => ({ tool: c }) as unknown as Capability,
    )
    const outcome = await delegate({
      role,
      task,
      capabilities,
      parentConversationId: ctx.conversationId,
      actor: ctx.actor ?? defaultActor,
      bridge: ctx.bridge,
      ...(ctx.runtimeStore ? { runtimeStore: ctx.runtimeStore } : {}),
      ...(ctx.runId ? { parentRunId: ctx.runId } : {}),
      // D5-arch-align §20 #5 (opt-in): thread parent tool allowlist into
      // delegate. Map string-tool-name to Capability brand so type contract
      // holds. When parentAllowedToolNames is undefined, no subset check
      // (legacy / CLI / service-to-service paths).
      ...(ctx.parentAllowedToolNames
        ? {
            parentAllowlist: ctx.parentAllowedToolNames.map(
              (n) => ({ tool: n }) as unknown as Capability,
            ),
          }
        : {}),
      ...(ctx.wechatUserId ? { subject: ctx.wechatUserId } : {}),
      ...(ctx.wechatUserId ? { notifySubject: ctx.wechatUserId } : {}),
    })
    writeSubagentAudit(ctx.runtimeStore, {
      ts: new Date().toISOString(),
      kind: "delegation",
      parentConversationId: ctx.conversationId,
      childConversationId: outcome.childConversationId,
      role,
      task,
      capabilities: effectiveCaps,
    })
    if (ctx.wechatUserId) {
      recordChildRunDelegated({
        userId: ctx.wechatUserId,
        projectId: (ctx.projectId ?? "wechat").trim() || "wechat",
        childRunId: outcome.childRunId,
        role,
        task,
        ...(ctx.env === undefined ? {} : { env: ctx.env }),
      })
    }
    return {
      ok: true,
      output: outcome.childRunId
        ? `任务已委派给 ${outcome.role} 子代理（child run: ${outcome.childRunId}, conversation: ${outcome.childConversationId}）。子代理运行后会自动回复。`
        : `任务已委派给 ${outcome.role} 子代理（child conversation: ${outcome.childConversationId}）。子代理运行后会自动回复。`,
    }
  })
}

/**
 * Provider-agnostic tool descriptors (LLMTool shape) for the wechat
 * butler. The R8.x.3.3 loop passes these to the LLM adapter via the
 * `tools` option so the model can decide whether to call a tool.
 *
 * Keep descriptions concrete: the model uses them to decide which
 * tool to invoke and what arguments to pass.
 */
export const WEIBUTLER_LLM_TOOLS: readonly LLMTool[] = [
  {
    name: "recall_history",
    description:
      "Recall the most recent conversation turns (messages from the runtime store, with event_store fallback). Pass an optional `limit` (default 5, max 20). Returns a numbered list with role/type and content.",
    parameters: {
      type: "object",
      properties: {
        limit: {
          type: "number",
          description: "Maximum number of recent turns to recall (1-20).",
        },
      },
    },
  },
  {
    name: "recall_durable_memory",
    description:
      "Search confirmed Durable Memory (owner preferences/facts). Optional `query` substring filter and `limit` (default 5). This is not conversation transcript and never invents memories from summaries.",
    parameters: {
      type: "object",
      properties: {
        query: { type: "string", description: "Optional keyword filter." },
        limit: { type: "number", description: "Max memories to return (1-20)." },
      },
    },
  },
  {
    name: "recall_document",
    description:
      "Search ingested documents by keyword over extracted text (plaintext/markdown/pdf-with-preextracted-text). Optional `query` and `limit` (default 3). Not a vector RAG index.",
    parameters: {
      type: "object",
      properties: {
        query: { type: "string", description: "Optional keyword filter." },
        limit: { type: "number", description: "Max documents to return (1-10)." },
      },
    },
  },
  {
    name: "recall_project_knowledge",
    description:
      "Search Project Knowledge (ingested notes, file snapshots, promoted documents). Recalls the current project by default. Pass `projectId` to recall a specific project (including other projects) or `projects` for a comma-separated list / `*` for all projects (results are tagged with their project). Optional `query` substring filter and `limit` (default 5). Does not search personal Durable Memory or invent facts.",
    parameters: {
      type: "object",
      properties: {
        query: { type: "string", description: "Optional keyword filter." },
        limit: { type: "number", description: "Max items to return (1-20)." },
        projectId: {
          type: "string",
          description: "Optional project id override (can be any project).",
        },
        projects: {
          type: "string",
          description:
            "Optional comma-separated project id list, or `*` for all projects. Takes precedence over `projectId`.",
        },
      },
    },
  },
  {
    name: "get_current_time",
    description:
      "Return the current time in Asia/Shanghai (UTC+8) as a formatted Chinese string (e.g. '当前时区: Asia/Shanghai (UTC+8) 2026年8月15日 星期五 07:26:41'). Use when the user asks about the current time or date and a precise answer matters.",
    parameters: {
      type: "object",
      properties: {},
    },
  },
  {
    name: "greet_with_time",
    description:
      "Return a Chinese time-of-day greeting (早晨好/上午好/中午好/下午好/晚上好/夜深了) based on the current hour in Asia/Shanghai. Use when the user greets you or you want a natural opening line that reflects the time of day.",
    parameters: {
      type: "object",
      properties: {},
    },
  },
  {
    name: "summarize_today",
    description:
      "Return a summary of butler activity for this conversation in the last 24 hours (message roles when using the relational read model, or event types when falling back to event_store). Use when the user asks '今天做了什么' or wants a quick activity recap.",
    parameters: {
      type: "object",
      properties: {},
    },
  },
  {
    name: "read_file",
    description:
      "Read a UTF-8 text file inside the butler workspace. Pass `path` relative to the workspace root (absolute paths outside the workspace are rejected). Max 64KiB. Use when you need the contents of a project file.",
    parameters: {
      type: "object",
      properties: {
        path: { type: "string", description: "File path relative to the workspace root." },
      },
      required: ["path"],
    },
  },
  {
    name: "write_file",
    description:
      "Write UTF-8 text to a file inside the butler workspace. Pass `path` relative to the workspace root and full `content`. Creates parent directories when needed. Max 64KiB. Requires owner confirmation before executing.",
    parameters: {
      type: "object",
      properties: {
        path: { type: "string", description: "File path relative to the workspace root." },
        content: { type: "string", description: "Full UTF-8 text to write." },
      },
      required: ["path", "content"],
    },
  },
  {
    name: "run_command",
    description:
      'Run a short allowlisted command in the workspace (no shell). Pass `argv` as a string array, e.g. ["ls", "-la"], ["python3", "-c", "print(1)"], or ["rg", "TODO", "src"]. Allowed programs: cat, date, echo, git, grep, head, ls, node, pnpm, pwd, python3, rg, wc. Arguments cannot contain \'..\' or start with \'/\'. bash/rm/curl and similar are rejected.',
    parameters: {
      type: "object",
      properties: {
        argv: {
          type: "array",
          items: { type: "string" },
          description: "Program name plus arguments. First element must be an allowlisted command.",
        },
      },
      required: ["argv"],
    },
  },
  {
    name: "send_wechat_file",
    description:
      "Send an image or file from the butler workspace to the current WeChat user. Pass `path` relative to the workspace root (paths outside the workspace are rejected). Optional `caption` is sent as a text message first. Use when the user asks to receive a local file or generated image on WeChat. Max size matches inbound media (default 8MiB).",
    parameters: {
      type: "object",
      properties: {
        path: { type: "string", description: "File path relative to the workspace root." },
        caption: {
          type: "string",
          description: "Optional text sent before the attachment.",
        },
      },
      required: ["path"],
    },
  },
  {
    name: "delegate_to_subagent",
    description:
      "Delegate a task to a subagent. The subagent runs in the background and returns the result later via its own child conversation stream. Use this when the user's request requires capabilities you don't have directly (e.g., code execution, file operations, web search) or when you want a long-running task to happen asynchronously while you keep replying to the user.",
    parameters: {
      type: "object",
      properties: {
        task: {
          type: "string",
          description:
            "Description of the task to delegate. Be specific about what the subagent should do.",
        },
        role: {
          type: "string",
          description:
            "Optional role hint for the subagent (e.g. 'developer', 'researcher', 'reviewer'). Defaults to 'general'.",
        },
        capabilities: {
          type: "array",
          items: { type: "string" },
          description:
            "Optional list of capability tool names the subagent may use. Must come from the allowlist (general, get_current_time, summarize_today, recall_history, read_file, write_file, run_command). Defaults to ['general'] when unspecified.",
        },
      },
      required: ["task"],
    },
  },
]

/**
 * `recall_durable_memory` — explicit keyword recall over confirmed Durable Memory.
 * Does not read Transcript; does not invent facts from compaction.
 */
export function makeRecallDurableMemoryTool(ctx: ButlerToolContext): ToolDefinition {
  return makeTool("recall_durable_memory", "low", async (args) => {
    const store = ctx.durableMemoryStore
    if (!store) {
      return { ok: false, reason: "durable memory store unavailable" }
    }
    const subject = (ctx.memorySubject ?? "").trim() || "owner"
    const query = typeof args["query"] === "string" ? args["query"] : ""
    const limitRaw = typeof args["limit"] === "number" ? args["limit"] : 5
    const limit = Math.min(20, Math.max(1, Math.floor(limitRaw)))
    const { selectDurableMemoriesForWorkingSet } =
      await import("@butler/domain/knowledge/durable-memory.js")
    const records = await store.listBySubject({ subject, status: "confirmed", limit: 40 })
    const selected = selectDurableMemoriesForWorkingSet({
      records,
      nowMs: Date.now(),
      query,
      limit,
    })
    if (selected.length === 0) {
      return { ok: true, output: "（无匹配的已确认 Durable Memory）" }
    }
    const lines = selected.map(
      (r, i) =>
        `${i + 1}. [${r.id.slice(0, 8)} conf=${Math.round(r.confidence * 100)}%] ${r.content}`,
    )
    return { ok: true, output: lines.join("\n") }
  })
}

/**
 * `recall_document` — keyword recall over ingested documents (extracted text).
 * Not a vector index; does not invent documents.
 */
export function makeRecallDocumentTool(ctx: ButlerToolContext): ToolDefinition {
  return makeTool("recall_document", "low", async (args) => {
    const store = ctx.documentStore
    if (!store) {
      return { ok: false, reason: "document store unavailable" }
    }
    const subject = (ctx.memorySubject ?? "").trim() || "owner"
    const query = typeof args["query"] === "string" ? args["query"] : ""
    const limitRaw = typeof args["limit"] === "number" ? args["limit"] : 3
    const limit = Math.min(10, Math.max(1, Math.floor(limitRaw)))
    const { formatDocumentSnippet, selectDocumentsForRecall } =
      await import("@butler/domain/knowledge/document-ingest.js")
    const records = await store.listBySubject({ subject, limit: 40 })
    const selected = selectDocumentsForRecall({ records, query, limit })
    if (selected.length === 0) {
      return { ok: true, output: "（无匹配的已 ingest 文档）" }
    }
    return {
      ok: true,
      output: selected.map((r, i) => `${i + 1}. ${formatDocumentSnippet(r)}`).join("\n\n"),
    }
  })
}

/**
 * `recall_project_knowledge` — keyword recall over project-scoped ingest.
 * Recalls the current project by default; `projectId` can target any project
 * and `projects` supports a comma-separated list or `*` for all projects
 * (G5 cross-project recall).
 */
export function makeRecallProjectKnowledgeTool(ctx: ButlerToolContext): ToolDefinition {
  return makeTool("recall_project_knowledge", "low", async (args) => {
    const store = ctx.projectKnowledgeStore
    if (!store) {
      return { ok: false, reason: "project knowledge store unavailable" }
    }
    const {
      expandRecallProjectIds,
      formatCrossProjectRecall,
      formatProjectKnowledgeSnippet,
      resolveProjectKnowledgeInboundProjectId,
    } = await import("@butler/domain/knowledge/project-knowledge.js")
    const env = ctx.env ?? process.env
    const contextProjectId = resolveProjectKnowledgeInboundProjectId(
      (ctx.projectId ?? "").trim(),
      env,
    )
    const requestedRaw =
      typeof args["projectId"] === "string" && args["projectId"].trim()
        ? args["projectId"].trim()
        : ""
    const requestedProjectId = requestedRaw
      ? resolveProjectKnowledgeInboundProjectId(requestedRaw, env)
      : ""
    const projectsRaw =
      typeof args["projects"] === "string" && args["projects"].trim() ? args["projects"].trim() : ""
    const allProjectIds = projectsRaw === "*" ? await store.listAllProjects() : undefined
    const expanded = expandRecallProjectIds({
      contextProjectId,
      requestedProjectId,
      projects: projectsRaw,
      ...(allProjectIds === undefined ? {} : { allProjectIds }),
    })
    if (!expanded.ok) {
      return { ok: false, reason: expanded.reason }
    }
    const query = typeof args["query"] === "string" ? args["query"] : ""
    const limitRaw = typeof args["limit"] === "number" ? args["limit"] : 5
    const limit = Math.min(20, Math.max(1, Math.floor(limitRaw)))
    const perProjectLimit = Math.max(1, Math.ceil(limit / expanded.projectIds.length))
    const records = await store.listByProjects({
      projectIds: expanded.projectIds,
      perProjectLimit,
    })
    const byProject = expanded.projectIds
      .map((projectId) => ({
        projectId,
        records: records.filter((r) => r.projectId === projectId),
      }))
      .filter((g) => g.records.length > 0)
    const formatted = formatCrossProjectRecall({
      query,
      limit,
      byProject,
      formatSnippet: formatProjectKnowledgeSnippet,
    })
    if (formatted === null) {
      return { ok: true, output: "（无匹配的项目知识条目）" }
    }
    return { ok: true, output: formatted }
  })
}

/**
 * Build the sandboxed-tool context, carrying the runtime-injected audit
 * context into the read_file / write_file / run_command exec points (D47).
 * Observation only — the audit context never issues permissions.
 */
function workspaceToolCtx(ctx: ButlerToolContext): WorkspaceToolContext {
  const subject = ctx.wechatUserId ?? ctx.actor?.id
  const audit = ctx.runtimeStore
    ? {
        runtimeStore: ctx.runtimeStore,
        conversationId: ctx.conversationId,
        ...(ctx.runId === undefined ? {} : { runId: ctx.runId }),
        ...(subject === undefined ? {} : { subject }),
      }
    : undefined
  return {
    ...(ctx.workspaceRoot ? { workspaceRoot: ctx.workspaceRoot } : {}),
    ...(audit ? { audit } : {}),
  }
}

/**
 * Build the runtime ToolDefinition set wired to the current
 * EventBridge + conversationId. The butler loop owns this — tools
 * hold a reference to the bridge, not a global singleton.
 */
export function makeWeibutlerTools(ctx: ButlerToolContext): readonly ToolDefinition[] {
  const env = ctx.env ?? process.env
  const mcp =
    ctx.mcpBundle && ctx.mcpBundle.runtimeTools.length > 0
      ? ctx.mcpBundle.runtimeTools
      : loadMcpToolDefinitions(env, ctx.mcp ?? {})
  const core = [
    makeRecallHistoryTool(ctx),
    makeRecallDurableMemoryTool(ctx),
    makeRecallDocumentTool(ctx),
    makeRecallProjectKnowledgeTool(ctx),
    makeGetCurrentTimeTool(),
    makeGreetWithTimeTool(),
    makeSummarizeTodayTool(ctx),
    makeReadFileTool(workspaceToolCtx(ctx)),
    makeWriteFileTool(workspaceToolCtx(ctx)),
    makeRunCommandTool(workspaceToolCtx(ctx)),
    makeSendWechatFileTool(ctx),
  ]
  if (isSubagentEnabled(env)) {
    core.push(makeDelegateToSubagentTool(ctx))
  }
  return enrichDeclaredSchemas([...core, ...mcp])
}

/**
 * P3-2: attach each core tool's `inputSchema` from the single trusted source
 * WEIBUTLER_LLM_TOOLS.parameters. MCP tools already carry their schema in
 * makeMcpToolDefinition; tools without a matching LLM row pass through unchanged.
 * Never fabricates a schema when there is no real source.
 */
function enrichDeclaredSchemas(tools: readonly ToolDefinition[]): readonly ToolDefinition[] {
  const paramsByName = new Map(WEIBUTLER_LLM_TOOLS.map((t) => [t.name, t.parameters]))
  return tools.map((t) => {
    const params = paramsByName.get(t.name as string)
    if (!params) return t
    return { ...t, declared: { ...t.declared, inputSchema: params } }
  })
}

/** LLM tool list including opt-in MCP and subagent descriptors when enabled. */
export function llmToolsForButler(
  ctx: Pick<ButlerToolContext, "env" | "mcp" | "mcpBundle"> = {},
): readonly LLMTool[] {
  const env = ctx.env ?? process.env
  const mcp =
    ctx.mcpBundle && ctx.mcpBundle.llmTools.length > 0
      ? ctx.mcpBundle.llmTools
      : loadMcpLlmTools(env, ctx.mcp ?? {})
  const core = isSubagentEnabled(env)
    ? WEIBUTLER_LLM_TOOLS
    : WEIBUTLER_LLM_TOOLS.filter((t) => t.name !== "delegate_to_subagent")
  return [...core, ...mcp]
}

/**
 * Look up a ToolDefinition by name from a tool set. Returns undefined
 * if the name does not match — the caller is responsible for handling
 * the unknown-tool case (the R8.x.3.3 loop logs + continues).
 */
export function findTool(
  tools: readonly ToolDefinition[],
  name: string,
): ToolDefinition | undefined {
  return tools.find((t) => (t.name as string) === name)
}
