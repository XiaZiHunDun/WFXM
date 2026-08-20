import type { EventBridge } from "@butler/runtime/bridge.js"
import type { RuntimeStore } from "@butler/domain/runtime.js"
import type { LLMTool } from "@butler/adapters"
import {
  ALLOWED_CAPABILITIES,
  delegate,
  type Capability,
} from "@butler/runtime/delegate-runtime.js"
import type { ToolDefinition } from "@butler/runtime/tool-runtime.js"
import { writeSubagentAudit } from "./audit-service.js"
import { makeSendWechatFileTool } from "./send-wechat-file.js"
import { makeReadFileTool, makeRunCommandTool } from "./workspace-tools.js"
import { loadMcpToolDefinitions, loadMcpLlmTools, type McpToolsOptions } from "./mcp-tools.js"
import type { McpToolBundle } from "./mcp-bootstrap.js"

/**
 * Minimal context passed to tool handlers. The butler loop wires the
 * current EventBridge + conversation id so tools like `recall_history`
 * can read from event_store without taking a global dependency.
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
  /** Sandbox root for read_file / run_command. Defaults to cwd / env. */
  readonly workspaceRoot?: string
  /** Current inbound WeChat user; required by send_wechat_file. */
  readonly wechatUserId?: string
  readonly wechatContextToken?: string
  readonly env?: NodeJS.ProcessEnv
  /** Inject MCP discovery/invoke for tests; production uses wiring.mcp from bootstrap. */
  readonly mcp?: McpToolsOptions
  readonly mcpBundle?: McpToolBundle
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
 * `recall_history` — query the event_store for the most recent
 * conversation events and return them as a compact string the LLM
 * can quote in its reply. Marked low-risk: it only reads.
 */
export function makeRecallHistoryTool(ctx: ButlerToolContext): ToolDefinition {
  return {
    name: "recall_history" as ToolDefinition["name"],
    risk: "low",
    async run(args: Record<string, unknown>): Promise<
      | {
          readonly ok: true
          readonly output: unknown
        }
      | { readonly ok: false; readonly reason: string }
    > {
      const limitRaw = args["limit"]
      const limit =
        typeof limitRaw === "number" && Number.isFinite(limitRaw) && limitRaw > 0
          ? Math.min(Math.floor(limitRaw), 20)
          : 5
      try {
        const events = await ctx.bridge.loadStream(ctx.conversationId)
        const recent = events.slice(-limit)
        const lines = recent.map((e, i) => {
          const payload = e.payload as Record<string, unknown>
          const content =
            typeof payload["content"] === "string" ? (payload["content"] as string) : ""
          return `${i + 1}. [${e.eventType}] ${content}`
        })
        return {
          ok: true,
          output: lines.length > 0 ? lines.join("\n") : "(no prior events)",
        }
      } catch (err) {
        return { ok: false, reason: err instanceof Error ? err.message : String(err) }
      }
    },
  }
}

/**
 * `get_current_time` — R8.x.5: return the wall-clock time formatted in
 * Asia/Shanghai (UTC+8) with Chinese date + weekday labels. The label
 * is included so the model can quote it without converting between
 * zones. Marked low-risk: pure read, no side effects.
 */
export function makeGetCurrentTimeTool(): ToolDefinition {
  return {
    name: "get_current_time" as ToolDefinition["name"],
    risk: "low",
    async run(_args: Record<string, unknown>): Promise<
      | {
          readonly ok: true
          readonly output: unknown
        }
      | { readonly ok: false; readonly reason: string }
    > {
      try {
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
      } catch (err) {
        return { ok: false, reason: err instanceof Error ? err.message : String(err) }
      }
    },
  }
}

/**
 * `greet_with_time` — return a Chinese greeting based on the local
 * hour in Asia/Shanghai. Lets the model greet the user naturally
 * (早晨好 / 上午好 / 中午好 / 下午好 / 晚上好 / 夜深了) without having
 * to map an hour to a greeting inline. Marked low-risk: pure read.
 */
export function makeGreetWithTimeTool(): ToolDefinition {
  return {
    name: "greet_with_time" as ToolDefinition["name"],
    risk: "low",
    async run(_args: Record<string, unknown>): Promise<
      | {
          readonly ok: true
          readonly output: unknown
        }
      | { readonly ok: false; readonly reason: string }
    > {
      try {
        const hourRaw = new Intl.DateTimeFormat("en-US", {
          timeZone: SHANGHAI_TIMEZONE,
          hour: "numeric",
          hour12: false,
        }).format(new Date())
        const hour = Number.parseInt(hourRaw, 10)
        const safeHour = Number.isFinite(hour) ? hour : 0
        const greeting = pickGreeting(safeHour)
        return { ok: true, output: greeting }
      } catch (err) {
        return { ok: false, reason: err instanceof Error ? err.message : String(err) }
      }
    },
  }
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
 * `summarize_today` — read the entire event_store for the current
 * conversation and return a 24-hour window summary, broken down by
 * event type. Marked low-risk: pure read. The EventBridge does not
 * expose a generic query API yet, so the summary is derived from
 * `loadStream` (the same source `recall_history` uses). If the bridge
 * errors, the tool returns an error envelope rather than throwing.
 */
export function makeSummarizeTodayTool(ctx: ButlerToolContext): ToolDefinition {
  return {
    name: "summarize_today" as ToolDefinition["name"],
    risk: "low",
    async run(_args: Record<string, unknown>): Promise<
      | {
          readonly ok: true
          readonly output: unknown
        }
      | { readonly ok: false; readonly reason: string }
    > {
      try {
        const events = await ctx.bridge.loadStream(ctx.conversationId)
        const cutoff = Date.now() - 24 * 60 * 60 * 1000
        const recent = events.filter((e) => {
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
      } catch (err) {
        return { ok: false, reason: err instanceof Error ? err.message : String(err) }
      }
    },
  }
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
  return {
    name: "delegate_to_subagent" as ToolDefinition["name"],
    risk: "medium",
    async run(args: Record<string, unknown>): Promise<
      | {
          readonly ok: true
          readonly output: unknown
        }
      | { readonly ok: false; readonly reason: string }
    > {
      const taskRaw = args["task"]
      const roleRaw = args["role"]
      const capsRaw = args["capabilities"]
      const task = typeof taskRaw === "string" ? taskRaw.trim() : ""
      if (!task) return { ok: false, reason: "task is required" }
      const role = typeof roleRaw === "string" && roleRaw.trim() ? roleRaw.trim() : "general"
      const requestedCaps: readonly string[] = Array.isArray(capsRaw)
        ? capsRaw.filter((c): c is string => typeof c === "string")
        : []
      const effectiveCaps = requestedCaps.length > 0 ? requestedCaps : ["general"]
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
      try {
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
        return {
          ok: true,
          output: `任务已委派给 ${outcome.role} 子代理（child conversation: ${outcome.childConversationId}）。子代理运行后会自动回复。`,
        }
      } catch (err) {
        return { ok: false, reason: err instanceof Error ? err.message : String(err) }
      }
    },
  }
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
      "Recall the most recent conversation events from this conversation's event_store. Pass an optional `limit` (default 5, max 20) to control how many recent messages are returned. Returns a numbered list of past events with their type and content.",
    parameters: {
      type: "object",
      properties: {
        limit: {
          type: "number",
          description: "Maximum number of recent events to recall (1-20).",
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
      "Return a summary of butler activity for this conversation in the last 24 hours, broken down by event type (e.g. 'AssistantMessageProduced: 4, ConversationStarted: 1'). Use when the user asks '今天做了什么' or wants a quick activity recap.",
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
            "Optional list of capability tool names the subagent may use. Must come from the allowlist (general, get_current_time, summarize_today, recall_history, read_file, run_command). Defaults to ['general'] when unspecified.",
        },
      },
      required: ["task"],
    },
  },
]

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
  return [
    makeRecallHistoryTool(ctx),
    makeGetCurrentTimeTool(),
    makeGreetWithTimeTool(),
    makeSummarizeTodayTool(ctx),
    makeReadFileTool(ctx),
    makeRunCommandTool(ctx),
    makeSendWechatFileTool(ctx),
    makeDelegateToSubagentTool(ctx),
    ...mcp,
  ]
}

/** LLM tool list including opt-in MCP descriptors when enabled. */
export function llmToolsForButler(
  ctx: Pick<ButlerToolContext, "env" | "mcp" | "mcpBundle"> = {},
): readonly LLMTool[] {
  const env = ctx.env ?? process.env
  const mcp =
    ctx.mcpBundle && ctx.mcpBundle.llmTools.length > 0
      ? ctx.mcpBundle.llmTools
      : loadMcpLlmTools(env, ctx.mcp ?? {})
  return [...WEIBUTLER_LLM_TOOLS, ...mcp]
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
