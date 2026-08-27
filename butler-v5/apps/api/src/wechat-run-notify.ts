import {
  DEFAULT_ILINK_BASE_URL,
  ilinkSendMessage,
  type ILinkClientConfig,
} from "@butler/adapters"
import { appendFileSync } from "node:fs"
import type { EventBridge } from "@butler/persistence/event-bridge.js"

function envTruthy(raw: string | undefined): boolean {
  if (!raw) return false
  const text = raw.trim().toLowerCase()
  return text === "1" || text === "true" || text === "yes" || text === "on"
}

/** Proactive WeChat push when long runs / subagents finish (BUTLER_V5_RUN_NOTIFY_ENABLED). */
export function isRunNotifyEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return envTruthy(env["BUTLER_V5_RUN_NOTIFY_ENABLED"])
}

export function formatTaskRunCompletionNotify(input: {
  readonly taskId: string
  readonly title: string
  readonly decision: string
  readonly reply: string
  readonly ok: boolean
}): string {
  const status = input.ok ? "完成" : "失败"
  const short = input.taskId.slice(0, 8)
  const excerpt = input.reply.trim().slice(0, 400)
  return [
    `【待办${status}】${short} ${input.title.slice(0, 60)}`,
    `决策：${input.decision}`,
    excerpt ? `回复：${excerpt}` : "",
  ]
    .filter((line) => line.length > 0)
    .join("\n")
}

export function formatSubagentCompletionNotify(input: {
  readonly role: string
  readonly task: string
  readonly reply: string
  readonly ok: boolean
}): string {
  const status = input.ok ? "完成" : "失败"
  const excerpt = input.reply.trim().slice(0, 400)
  return [
    `【子代理${status}】${input.role}`,
    `任务：${input.task.slice(0, 120)}`,
    excerpt ? `回复：${excerpt}` : "",
  ]
    .filter((line) => line.length > 0)
    .join("\n")
}

export async function resolveWechatUserFromConversation(
  bridge: EventBridge,
  conversationId: string,
): Promise<string | null> {
  try {
    const events = await bridge.loadStream(conversationId)
    for (const row of events) {
      if (row.eventType !== "ConversationStarted") continue
      const ev = row.payload as { fromUserId?: unknown }
      if (typeof ev.fromUserId === "string" && ev.fromUserId.trim()) {
        return ev.fromUserId.trim()
      }
    }
  } catch {
    // best-effort
  }
  return null
}

function ilinkClientFromEnv(env: NodeJS.ProcessEnv): ILinkClientConfig | null {
  if (!envTruthy(env["BUTLER_V5_ILINK_ENABLED"])) return null
  const token = (env["WECHAT_TOKEN"] ?? "").trim()
  if (!token) return null
  const baseUrl = (env["WECHAT_BASE_URL"] ?? env["ILINK_BASE_URL"] ?? DEFAULT_ILINK_BASE_URL).trim()
  return { baseUrl, token }
}

export async function sendWechatProactiveNotify(args: {
  readonly to: string
  readonly text: string
  readonly env?: NodeJS.ProcessEnv
}): Promise<{ readonly ok: true } | { readonly ok: false; readonly reason: string }> {
  const env = args.env ?? process.env
  if (!isRunNotifyEnabled(env)) {
    return { ok: false, reason: "run notify disabled" }
  }
  const to = args.to.trim()
  const text = args.text.trim()
  if (!to || !text) {
    return { ok: false, reason: "empty recipient or message" }
  }
  const mockOutbox = (env["BUTLER_V5_RUN_NOTIFY_MOCK_OUTBOX"] ?? "").trim()
  if (mockOutbox) {
    try {
      appendFileSync(
        mockOutbox,
        `${JSON.stringify({ to, text, ts: new Date().toISOString() })}\n`,
      )
      return { ok: true }
    } catch (err) {
      return {
        ok: false,
        reason: err instanceof Error ? err.message : String(err),
      }
    }
  }
  const client = ilinkClientFromEnv(env)
  if (!client) {
    return { ok: false, reason: "iLink not configured" }
  }
  try {
    const result = await ilinkSendMessage(client, { to, text })
    if (!result.ok) {
      return { ok: false, reason: result.reason ?? "ilink send failed" }
    }
    return { ok: true }
  } catch (err) {
    return {
      ok: false,
      reason: err instanceof Error ? err.message : String(err),
    }
  }
}

export async function notifySubagentCompletion(args: {
  readonly bridge: EventBridge
  readonly parentConversationId: string
  readonly notifySubject?: string
  readonly role: string
  readonly task: string
  readonly reply: string
  readonly ok: boolean
  readonly env?: NodeJS.ProcessEnv
}): Promise<void> {
  const env = args.env ?? process.env
  if (!isRunNotifyEnabled(env)) return
  const explicit = args.notifySubject?.trim() ?? ""
  const to =
    explicit || (await resolveWechatUserFromConversation(args.bridge, args.parentConversationId))
  if (!to) return
  await sendWechatProactiveNotify({
    to,
    text: formatSubagentCompletionNotify({
      role: args.role,
      task: args.task,
      reply: args.reply,
      ok: args.ok,
    }),
    env,
  })
}
