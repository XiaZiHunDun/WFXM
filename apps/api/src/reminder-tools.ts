/**
 * Reminder tools: create / list / cancel. Low-risk and side-effect free —
 * they only write the reminder table; the worker sends plain text later.
 *
 * Registered only when BUTLER_V5_REMINDERS_ENABLED=1.
 */
import type { LLMTool } from "@butler/adapters"
import type { ReminderRecord, ReminderRepeat, ReminderStore } from "@butler/persistence"
import { makeToolName, type RunResult, type ToolDefinition } from "@butler/runtime/tool-runtime.js"
import type { ButlerToolContext } from "./tools.js"
import { parseReminderConfig } from "./reminder-config.js"
import {
  formatReminderSchedule,
  parseReminderTime,
  type ReminderTimeParseResult,
} from "./reminder-time.js"

export const REMINDER_TOOL_NAMES = ["create_reminder", "list_reminders", "cancel_reminder"] as const

export const REMINDER_LLM_TOOLS: readonly LLMTool[] = [
  {
    name: "create_reminder",
    description:
      "Create a personal reminder that the butler pushes to the owner as a plain text message at the given time. Use when the user says things like '明天 9:30 提醒我交周报'. Convert the natural-language time into an absolute Asia/Shanghai time and pass `fireAt` as `YYYY-MM-DD HH:mm`. `repeat` is once (default), daily or weekly. Do NOT guess: if the time is unclear or in the past, ask the user once for a concrete time instead of calling this tool.",
    parameters: {
      type: "object",
      properties: {
        content: { type: "string", description: "What to remind the owner about (max 500 chars)." },
        fireAt: {
          type: "string",
          description:
            "Absolute time in Asia/Shanghai, formatted as YYYY-MM-DD HH:mm (e.g. 2026-11-24 09:30).",
        },
        repeat: {
          type: "string",
          enum: ["once", "daily", "weekly"],
          description: "once (default), daily, or weekly at the same time.",
        },
      },
      required: ["content", "fireAt"],
    },
  },
  {
    name: "list_reminders",
    description:
      "List the owner's active reminders in Asia/Shanghai time. Use when the user asks '我有哪些提醒' / '提醒列表'. Returns an empty notice when there are none.",
    parameters: { type: "object", properties: {} },
  },
  {
    name: "cancel_reminder",
    description:
      "Cancel one active reminder. Pass `id` when known, otherwise pass `query` with keywords from the reminder content. If more than one reminder matches, the tool returns the candidates so you can ask the owner which one to cancel.",
    parameters: {
      type: "object",
      properties: {
        id: { type: "string", description: "Reminder id (preferred when already listed)." },
        query: { type: "string", description: "Keyword from the reminder content." },
      },
    },
  },
]

function repeatOf(raw: unknown): ReminderRepeat | null {
  if (raw === undefined || raw === null || raw === "") return "once"
  if (raw === "once" || raw === "daily" || raw === "weekly") return raw
  return null
}

function ownerSubject(ctx: ButlerToolContext): string {
  return ctx.wechatUserId?.trim() || ctx.actor?.id || "owner"
}

function audit(
  ctx: ButlerToolContext,
  action: string,
  detail: Readonly<Record<string, unknown>>,
): void {
  const store = ctx.runtimeStore
  if (!store) return
  void store
    .appendAuditEvent({
      auditId: crypto.randomUUID(),
      runId: ctx.runId ?? null,
      conversationId: ctx.conversationId,
      correlationId: ctx.conversationId,
      action,
      actor: "owner-direct",
      subject: ownerSubject(ctx),
      detail,
      createdAt: new Date(),
    })
    .catch((err: unknown) => {
      // eslint-disable-next-line no-console -- operator log; audit must not break the tool
      console.error("[reminder-tools] appendAuditEvent failed:", err)
    })
}

function requireStore(ctx: ButlerToolContext): ReminderStore | null {
  return ctx.reminderStore ?? null
}

function lineFor(reminder: ReminderRecord): string {
  return `${formatReminderSchedule(reminder.fireAtMs, reminder.repeat)} ${reminder.content}`
}

export function makeCreateReminderTool(ctx: ButlerToolContext): ToolDefinition {
  return {
    name: makeToolName("create_reminder"),
    risk: "low",
    async run(args: Record<string, unknown>): Promise<RunResult> {
      try {
        const store = requireStore(ctx)
        if (!store) return { ok: false, reason: "提醒功能暂不可用，请联系管理员。" }
        const wechatUserId = ctx.wechatUserId?.trim()
        if (!wechatUserId) {
          return { ok: false, reason: "当前渠道不支持提醒，请在微信里创建。" }
        }
        const content = typeof args["content"] === "string" ? args["content"].trim() : ""
        if (!content) return { ok: false, reason: "请给出提醒内容。" }
        if (content.length > 500)
          return { ok: false, reason: "提醒内容过长，请控制在 500 字以内。" }

        const repeat = repeatOf(args["repeat"])
        if (repeat === null) {
          return { ok: false, reason: "重复方式只支持 once、daily 或 weekly。" }
        }
        const fireAtRaw = typeof args["fireAt"] === "string" ? args["fireAt"] : ""
        const nowMs = Date.now()
        const parsed: ReminderTimeParseResult = parseReminderTime({
          text: fireAtRaw,
          repeat,
          nowMs,
        })
        if (!parsed.ok) return { ok: false, reason: parsed.reason }

        const config = parseReminderConfig(ctx.env ?? process.env)
        const subject = ownerSubject(ctx)
        if ((await store.countActiveBySubject(subject)) >= config.maxPerOwner) {
          return {
            ok: false,
            reason: `提醒数量已达上限（${config.maxPerOwner} 条），请先取消部分提醒。`,
          }
        }

        const record: ReminderRecord = {
          id: crypto.randomUUID(),
          subject,
          wechatUserId,
          conversationId: ctx.conversationId,
          content,
          fireAtMs: parsed.fireAtMs,
          repeat,
          status: "active",
          attemptCount: 0,
          lastAttemptAtMs: null,
          lastError: null,
          firedAtMs: null,
          createdAtMs: nowMs,
          updatedAtMs: nowMs,
        }
        await store.create(record)
        audit(ctx, "reminder.created", {
          reminderId: record.id,
          repeat,
          fireAt: new Date(record.fireAtMs).toISOString(),
        })
        return {
          ok: true,
          output: `已设置提醒：${lineFor(record)}`,
          meta: { reminderId: record.id, repeat, fireAtMs: record.fireAtMs },
        }
      } catch (err) {
        return { ok: false, reason: err instanceof Error ? err.message : String(err) }
      }
    },
  }
}

export function makeListRemindersTool(ctx: ButlerToolContext): ToolDefinition {
  return {
    name: makeToolName("list_reminders"),
    risk: "low",
    async run(): Promise<RunResult> {
      try {
        const store = requireStore(ctx)
        if (!store) return { ok: false, reason: "提醒功能暂不可用，请联系管理员。" }
        const rows = await store.listActiveBySubject({ subject: ownerSubject(ctx) })
        if (rows.length === 0) return { ok: true, output: "当前没有提醒。" }
        const lines = rows.map((row, i) => `${i + 1}. ${lineFor(row)}`)
        return {
          ok: true,
          output: `当前提醒（${rows.length} 条）：\n${lines.join("\n")}`,
          meta: { reminderIds: rows.map((row) => row.id) },
        }
      } catch (err) {
        return { ok: false, reason: err instanceof Error ? err.message : String(err) }
      }
    },
  }
}

export function makeCancelReminderTool(ctx: ButlerToolContext): ToolDefinition {
  return {
    name: makeToolName("cancel_reminder"),
    risk: "low",
    async run(args: Record<string, unknown>): Promise<RunResult> {
      try {
        const store = requireStore(ctx)
        if (!store) return { ok: false, reason: "提醒功能暂不可用，请联系管理员。" }
        const subject = ownerSubject(ctx)
        const id = typeof args["id"] === "string" ? args["id"].trim() : ""
        const query = typeof args["query"] === "string" ? args["query"].trim().toLowerCase() : ""

        if (id) {
          const record = await store.get(id)
          if (!record || record.subject !== subject || record.status !== "active") {
            return { ok: false, reason: "未找到对应的提醒，可能已取消或已触发。" }
          }
          const cancelled = await store.cancel({ id, subject })
          if (!cancelled) return { ok: false, reason: "取消失败，请稍后重试。" }
          audit(ctx, "reminder.cancelled", { reminderId: id })
          return { ok: true, output: `已取消提醒：${lineFor(record)}` }
        }

        if (!query) return { ok: false, reason: "请给出要取消的提醒关键词或编号。" }
        const rows = await store.listActiveBySubject({ subject })
        const matches = rows.filter((row) => row.content.toLowerCase().includes(query))
        if (matches.length === 0) {
          return { ok: false, reason: "未找到匹配的提醒。" }
        }
        if (matches.length > 1) {
          const lines = matches.map((row, i) => `${i + 1}. ${lineFor(row)}`)
          return {
            ok: true,
            output: `找到多条匹配的提醒，请指定要取消的一条：\n${lines.join("\n")}`,
            meta: { reminderIds: matches.map((row) => row.id) },
          }
        }
        const target = matches[0]
        if (!target) return { ok: false, reason: "未找到匹配的提醒。" }
        const cancelled = await store.cancel({ id: target.id, subject })
        if (!cancelled) return { ok: false, reason: "取消失败，请稍后重试。" }
        audit(ctx, "reminder.cancelled", { reminderId: target.id })
        return { ok: true, output: `已取消提醒：${lineFor(target)}` }
      } catch (err) {
        return { ok: false, reason: err instanceof Error ? err.message : String(err) }
      }
    },
  }
}

export function makeReminderTools(ctx: ButlerToolContext): readonly ToolDefinition[] {
  return [makeCreateReminderTool(ctx), makeListRemindersTool(ctx), makeCancelReminderTool(ctx)]
}
