import { delegate } from "@butler/runtime/delegate-runtime.js"
import { defaultWechatConversationId } from "@butler/runtime/intake/conversation-id.js"
import { writeSubagentAudit } from "./audit-service.js"
import { getWechatActiveProjectId } from "./wechat-active-project.js"
import type { ButlerLoopResult } from "./wechat-inbound-butler.js"
import { safeOwnerError } from "./safe-owner-error.js"
import { isSubagentEnabled } from "./subagent-config.js"
import type { Wiring } from "./wiring.js"

function done(reply: string, traces: readonly string[]): ButlerLoopResult {
  return {
    reply,
    iterations: 0,
    toolCalls: 0,
    finalDecision: "Respond",
    traces: [...traces],
  }
}

function shortChildId(id: string): string {
  return id.slice(-8)
}

function parseDelegateCommand(content: string): { readonly role: string; readonly task: string } | null {
  const trimmed = content.trim()
  if (!trimmed.startsWith("/委派")) return null
  const rest = trimmed.slice("/委派".length).trim()
  if (!rest || rest === "状态" || rest.startsWith("状态")) return null
  const pipe = rest.indexOf("|")
  if (pipe >= 0) {
    const role = rest.slice(0, pipe).trim()
    const task = rest.slice(pipe + 1).trim()
    if (role && task) return { role, task }
  }
  return { role: "general", task: rest }
}

export async function tryWechatSubagentCommand(args: {
  readonly wiring: Wiring
  readonly fromUserId: string
  readonly content: string
  readonly env?: NodeJS.ProcessEnv
}): Promise<ButlerLoopResult | null> {
  const env = args.env ?? process.env
  const trimmed = args.content.trim()
  if (!trimmed.startsWith("/委派")) return null

  if (!isSubagentEnabled(env)) {
    return done(
      "Subagent 未启用。运行 scripts/cutover/enable-subagent-prod.sh 后重启 gateway。",
      ["wechat-subagent: disabled"],
    )
  }

  const subject = args.fromUserId.trim()
  const active = getWechatActiveProjectId(subject, env)

  if (trimmed === "/委派状态" || trimmed === "/委派 状态") {
    // D73 T5 (audit #19 SO-007): swap JSONL read (readRecentSubagentAudit)
    // for runtimeStore.listRecentAuditEvents — single source of truth matches
    // the dual-write at audit-service.ts:12. Pre-T5 readers waited on the
    // legacy JSONL path which only observed subagent events; the runtime
    // audit_events table is now the canonical source (D69 T1 pattern).
    const events = args.wiring.runtimeStore
      ? await args.wiring.runtimeStore.listRecentAuditEvents({
          windowMs: 7 * 24 * 3600 * 1000,
          limit: 12,
        })
      : []
    const subagentEvents = events.filter((e) => e.action.startsWith("subagent."))
    if (subagentEvents.length === 0) {
      return done("暂无委派记录。\n用法：/委派 <任务> 或 /委派 <角色> | <任务>", [
        "wechat-subagent: status empty",
      ])
    }
    const lines = ["最近委派："]
    for (const event of subagentEvents.slice().reverse()) {
      const kind = event.action.slice("subagent.".length) // delegation | completion | rejection
      const detail = (event.detail ?? {}) as {
        readonly childConversationId?: string
        readonly task?: string
        readonly role?: string
        readonly replyExcerpt?: string
        readonly reason?: string
      }
      const child = shortChildId(detail.childConversationId ?? "")
      const taskPreview = (detail.task ?? "").slice(0, 48)
      const role = event.subject // owner subject at write, not role (per audit-service.ts:25)
      if (kind === "delegation") {
        lines.push(`• [排队] ${role} · ${taskPreview} · child…${child}`)
      } else if (kind === "completion") {
        lines.push(
          `• [完成] ${role} · ${taskPreview} · ${detail.replyExcerpt?.slice(0, 40) ?? "—"}`,
        )
      } else if (kind === "rejection") {
        lines.push(`• [拒绝] ${role} · ${detail.reason ?? "—"}`)
      }
    }
    lines.push("", "新任务：/委派 <任务>")
    return done(lines.join("\n"), ["wechat-subagent: status"])
  }

  const parsed = parseDelegateCommand(trimmed)
  if (!parsed) {
    return done("用法：/委派 <任务> 或 /委派 <角色> | <任务>\n状态：/委派状态", [
      "wechat-subagent: usage",
    ])
  }

  const parentConversationId = defaultWechatConversationId(active, subject)
  try {
    const outcome = await delegate({
      role: parsed.role,
      task: parsed.task,
      capabilities: [{ tool: "general" as never }],
      parentConversationId,
      actor: { kind: "owner", id: subject },
      bridge: args.wiring.eventBridge,
      runtimeStore: args.wiring.runtimeStore,
      subject,
      notifySubject: subject,
    })
    writeSubagentAudit(args.wiring.runtimeStore, {
      ts: new Date().toISOString(),
      kind: "delegation",
      parentConversationId,
      childConversationId: outcome.childConversationId,
      role: parsed.role,
      task: parsed.task,
      capabilities: ["general"],
      // D58 T1: thread the owner who delegated so audit_events.subject
      // resolves to the human, not the subagent role.
      ownerSubject: subject,
    })
    return done(
      // D60 T2.4 (audit #3 F-08): drop child id, 8-hex run id, and
      // env-var knobs (3 jargon leaks). operator surfaces only.
      [
        `已委派给 ${parsed.role} 子代理（后台运行）。`,
        "完成后会主动推送微信。",
        "查看：/委派状态",
      ].join("\n"),
      [`wechat-subagent: delegated ${outcome.childConversationId}`],
    )
  } catch (err) {
    return done(
      safeOwnerError(err, "委派失败，请稍后重试", {
        operation: "wechat-subagent-delegate",
      }),
      ["wechat-subagent: delegate error"],
    )
  }
}
