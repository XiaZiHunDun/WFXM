import { delegate } from "@butler/runtime/delegate-runtime.js"
import { defaultWechatConversationId } from "@butler/runtime/intake/conversation-id.js"
import { readRecentSubagentAudit } from "./audit-log.js"
import { writeSubagentAudit } from "./audit-service.js"
import { getWechatActiveProjectId } from "./wechat-active-project.js"
import type { ButlerLoopResult } from "./wechat-inbound-butler.js"
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
    const rows = readRecentSubagentAudit(12, env)
    if (rows.length === 0) {
      return done("暂无委派记录。\n用法：/委派 <任务> 或 /委派 <角色> | <任务>", [
        "wechat-subagent: status empty",
      ])
    }
    const lines = ["最近委派："]
    for (const row of rows.slice().reverse()) {
      const child = shortChildId(row.childConversationId)
      const taskPreview = row.task.slice(0, 48)
      if (row.kind === "delegation") {
        lines.push(`• [排队] ${row.role} · ${taskPreview} · child…${child}`)
      } else if (row.kind === "completion") {
        lines.push(
          `• [完成] ${row.role} · ${taskPreview} · ${row.replyExcerpt?.slice(0, 40) ?? "—"}`,
        )
      } else if (row.kind === "rejection") {
        lines.push(`• [拒绝] ${row.role} · ${row.reason ?? "—"}`)
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
    })
    return done(
      [
        `已委派给 ${parsed.role} 子代理（后台运行）。`,
        `child: …${shortChildId(outcome.childConversationId)}`,
        outcome.childRunId ? `run: ${outcome.childRunId.slice(0, 8)}` : "",
        "完成后会主动推送微信（需 BUTLER_V5_RUN_NOTIFY_ENABLED=1）。",
        "查看：/委派状态",
      ]
        .filter((line) => line.length > 0)
        .join("\n"),
      [`wechat-subagent: delegated ${outcome.childConversationId}`],
    )
  } catch (err) {
    return done(
      `委派失败：${err instanceof Error ? err.message : String(err)}`,
      ["wechat-subagent: delegate error"],
    )
  }
}
