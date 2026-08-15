import type { EventBridge } from "@butler/runtime/bridge.js"
import type { LLMTool } from "@butler/adapters"
import { runTool, type ToolDefinition } from "./wechat-tool-runtime.js"

/**
 * Minimal context passed to tool handlers. The butler loop wires the
 * current EventBridge + conversation id so tools like `recall_history`
 * can read from event_store without taking a global dependency.
 */
export interface ButlerToolContext {
  readonly bridge: EventBridge
  readonly conversationId: string
}

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
 * `get_current_time` — return the current ISO timestamp. Marked
 * low-risk: pure read, no side effects. Useful for time-sensitive
 * questions without forcing the model to guess.
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
      return { ok: true, output: new Date().toISOString() }
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
      "Return the current server time as an ISO 8601 timestamp. Use when the user asks about the current time or date and a precise answer matters.",
    parameters: {
      type: "object",
      properties: {},
    },
  },
]

/**
 * Build the runtime ToolDefinition set wired to the current
 * EventBridge + conversationId. The butler loop owns this — tools
 * hold a reference to the bridge, not a global singleton.
 */
export function makeWeibutlerTools(ctx: ButlerToolContext): readonly ToolDefinition[] {
  return [makeRecallHistoryTool(ctx), makeGetCurrentTimeTool()]
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

export { runTool, type ToolDefinition }
