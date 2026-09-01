import {
  confirmDurableMemory,
  createDurableMemoryRecord,
} from "@butler/domain/knowledge/durable-memory.js"
import { getWechatActiveProjectId } from "./wechat-active-project.js"
import type { ButlerLoopResult } from "./wechat-inbound-butler.js"
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

function shortId(id: string): string {
  return id.slice(0, 8)
}

export async function tryWechatMemoryCommand(args: {
  readonly wiring: Wiring
  readonly fromUserId: string
  readonly content: string
  readonly env?: NodeJS.ProcessEnv
}): Promise<ButlerLoopResult | null> {
  const env = args.env ?? process.env
  const trimmed = args.content.trim()
  const subject = args.fromUserId.trim()
  const active = getWechatActiveProjectId(subject, env)
  const store = args.wiring.durableMemoryStore

  if (trimmed.startsWith("/记住")) {
    if (!store) {
      return done("Durable Memory 存储不可用。", ["wechat-memory: no store"])
    }
    const text = trimmed.slice("/记住".length).trim()
    if (!text) {
      return done("用法：/记住 <要记住的内容>", ["wechat-memory: remember usage"])
    }
    const created = createDurableMemoryRecord({
      subject,
      content: text,
      sourceKind: "owner",
      status: "confirmed",
      provenance: { note: `project:${active}` },
    })
    if (!created.ok) {
      return done(`无法保存：${created.reason}`, ["wechat-memory: create failed"])
    }
    const saved = await store.create(created.value)
    return done(
      `已记住（${shortId(saved.id)}）：${text.slice(0, 120)}${text.length > 120 ? "…" : ""}`,
      [`wechat-memory: remember ${saved.id}`],
    )
  }

  if (trimmed === "/记忆候选" || trimmed === "/memories-pending") {
    if (!store) {
      return done("Durable Memory 存储不可用。", ["wechat-memory: no store"])
    }
    const candidates = await store.listBySubject({ subject, status: "candidate", limit: 20 })
    const scoped = candidates.filter(
      (item) => !item.provenance.note || item.provenance.note.includes(active),
    )
    if (scoped.length === 0) {
      return done("暂无 candidate 记忆。", ["wechat-memory: candidates empty"])
    }
    const lines = [`候选 ${scoped.length} 条（${active}）：`]
    for (const item of scoped) {
      lines.push(
        `• ${shortId(item.id)} ${item.content.slice(0, 100)}${item.content.length > 100 ? "…" : ""}`,
      )
    }
    return done(lines.join("\n"), ["wechat-memory: candidates list"])
  }

  if (trimmed === "/记忆" || trimmed === "/memories") {
    if (!store) {
      return done("Durable Memory 存储不可用。", ["wechat-memory: no store"])
    }
    const confirmed = await store.listBySubject({ subject, status: "confirmed", limit: 10 })
    const scoped = confirmed.filter(
      (item) => !item.provenance.note || item.provenance.note.includes(active),
    )
    const items = scoped.length > 0 ? scoped : confirmed
    if (items.length === 0) {
      return done("暂无已确认记忆。使用 /记住 … 添加。", ["wechat-memory: empty"])
    }
    const lines = [`记忆（${active}，最近 ${items.length} 条）:`]
    for (const item of items) {
      lines.push(`• ${shortId(item.id)} ${item.content.slice(0, 100)}${item.content.length > 100 ? "…" : ""}`)
    }
    return done(lines.join("\n"), ["wechat-memory: list"])
  }

  if (trimmed.startsWith("/确认记忆")) {
    if (!store) {
      return done("Durable Memory 存储不可用。", ["wechat-memory: no store"])
    }
    const token = trimmed.slice("/确认记忆".length).trim()
    const candidates = await store.listBySubject({ subject, status: "candidate", limit: 20 })
    const target = token
      ? candidates.find((item) => item.id === token || shortId(item.id) === token)
      : candidates.at(-1)
    if (!target) {
      return done("没有待确认的 candidate 记忆。", ["wechat-memory: confirm none"])
    }
    const updated = await store.update(confirmDurableMemory(target, Date.now()))
    return done(
      `已确认记忆 ${shortId(updated.id)}。`,
      [`wechat-memory: confirm ${updated.id}`],
    )
  }

  return null
}
