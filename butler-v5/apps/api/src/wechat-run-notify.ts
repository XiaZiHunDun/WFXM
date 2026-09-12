import {
  DEFAULT_ILINK_BASE_URL,
  ilinkSendMessage,
  type ILinkClientConfig,
} from "@butler/adapters"
import { envTruthy } from "./env-util.js"
import { appendFileSync } from "node:fs"
import type { EventBridge } from "@butler/persistence/event-bridge.js"
import type { ChannelKind, ChannelPort } from "@butler/ports/core/channel.js"


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
  /** D2.4: prefer the WeChat ChannelPort from wiring when present. */
  readonly channels?: ReadonlyMap<ChannelKind, ChannelPort>
}): Promise<{ readonly ok: true } | { readonly ok: false; readonly reason: string }> {
  const env = args.env ?? process.env
  // D59 T5 (audit #3 F-07): push notify had 3 silent failure modes the
  // owner (and operator) couldn't diagnose. Log a structured stderr
  // line for each so the failure mode is recoverable from logs alone.
  if (!isRunNotifyEnabled(env)) {
    // eslint-disable-next-line no-console -- operator log when no logger injected
    console.error(
      `[wechat-run-notify] skipped reason=run_notify_disabled to=${args.to} hint=set BUTLER_V5_RUN_NOTIFY_ENABLED=1`,
    )
    return { ok: false, reason: "run notify disabled" }
  }
  const to = args.to.trim()
  const text = args.text.trim()
  if (!to || !text) {
    // eslint-disable-next-line no-console -- operator log when no logger injected
    console.error(
      `[wechat-run-notify] skipped reason=empty_recipient_or_message toLen=${args.to.length} textLen=${args.text.length}`,
    )
    return { ok: false, reason: "empty recipient or message" }
  }
  // D2.4 step 1: when Composition Root registers a WeChat ChannelPort, prefer the
  // port path; fall back to direct ilinkSendMessage when not present so tests /
  // existing call sites continue to work without DI changes.
  const port = args.channels?.get("wechat")
  if (port) {
    try {
      const result = await port.sendText({
        recipient: { address: to, channelKind: "wechat" },
        content: text,
      })
      if (!result.ok) {
        // eslint-disable-next-line no-console -- operator log when no logger injected
        console.error(
          `[wechat-run-notify] port-send-failed reason=${result.reason} to=${to}`,
        )
        return { ok: false, reason: result.reason }
      }
      return { ok: true }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      // eslint-disable-next-line no-console -- operator log when no logger injected
      console.error(`[wechat-run-notify] port-threw reason=${message} to=${to}`)
      return {
        ok: false,
        reason: message,
      }
    }
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
      const message = err instanceof Error ? err.message : String(err)
      // eslint-disable-next-line no-console -- operator log when no logger injected
      console.error(
        `[wechat-run-notify] mock-outbox-write-failed reason=${message} path=${mockOutbox}`,
      )
      return {
        ok: false,
        reason: message,
      }
    }
  }
  const client = ilinkClientFromEnv(env)
  if (!client) {
    // eslint-disable-next-line no-console -- operator log when no logger injected
    console.error(
      `[wechat-run-notify] skipped reason=ilink_not_configured to=${to} hint=set WECHAT_TOKEN+WECHAT_BASE_URL or BUTLER_V5_ILINK_ENABLED=1`,
    )
    return { ok: false, reason: "iLink not configured" }
  }
  try {
    const result = await ilinkSendMessage(client, { to, text })
    if (!result.ok) {
      // eslint-disable-next-line no-console -- operator log when no logger injected
      console.error(
        `[wechat-run-notify] ilink-send-failed reason=${result.reason ?? "ilink send failed"} to=${to}`,
      )
      return { ok: false, reason: result.reason ?? "ilink send failed" }
    }
    return { ok: true }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    // eslint-disable-next-line no-console -- operator log when no logger injected
    console.error(`[wechat-run-notify] ilink-threw reason=${message} to=${to}`)
    return {
      ok: false,
      reason: message,
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
