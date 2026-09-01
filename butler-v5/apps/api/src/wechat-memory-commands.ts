import {
  confirmDurableMemory,
  createDurableMemoryRecord,
  type DurableMemoryStatus,
} from "@butler/domain/knowledge/durable-memory.js"
import { findSimilarMemories } from "@butler/domain/knowledge/dedup.js"
import type { DurableMemoryStore } from "@butler/persistence"
import { getWechatActiveProjectId } from "./wechat-active-project.js"
import { parseDedupConfig } from "./dedup-config.js"
import type { ButlerLoopResult } from "./wechat-inbound-butler.js"
import type { Wiring } from "./wiring.js"

// G2 dedup (D41 T5) — module-scoped env-driven config (mirrors owner-routes T4).
// Wechat is owner-facing, no force bypass (owner cannot override via wechat —
// by design; wechat is more constrained than the HTTP API).
const dedupCfg = parseDedupConfig(process.env)

async function checkDedup(opts: {
  readonly store: DurableMemoryStore
  readonly subject: string
  readonly content: string
}): Promise<
  | {
      readonly existingMemoryId: string
      readonly similarity: number
      readonly status: DurableMemoryStatus
    }
  | null
> {
  if (!dedupCfg.enabled) return null
  try {
    const result = await findSimilarMemories({
      store: opts.store,
      subject: opts.subject,
      content: opts.content,
      threshold: dedupCfg.threshold,
      statuses: ["candidate", "confirmed", "rejected"],
      recentMs: dedupCfg.recentMs,
      limit: dedupCfg.limit,
    })
    if (result.best === null) return null
    return {
      existingMemoryId: result.best.id,
      similarity: result.best.similarity,
      status: result.best.status,
    }
  } catch (err) {
    // Fail-open: dedup DB error must not block owner writes (§20 #11
    // 守住 owner 自主权). Surface via stderr so operators can diagnose.
    // eslint-disable-next-line no-console -- operator log when no logger injected
    console.error(
      "[memory-dedup] check failed:",
      err instanceof Error ? err.message : String(err),
    )
    return null
  }
}

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
    // G2 dedup guard (D41 T5): block /记住 when a near-duplicate memory already
    // exists for the same subject. Wechat has no force bypass — owner cannot
    // override via this channel (by design; wechat is more constrained than
    // HTTP). Fail-open inside helper — DB errors fall through to create.
    const dedupHit = await checkDedup({
      store,
      subject: created.value.subject,
      content: created.value.content,
    })
    if (dedupHit !== null) {
      // eslint-disable-next-line no-console -- operator log when no logger injected
      console.error(
        `[memory-dedup] wechat hit existingId=${dedupHit.existingMemoryId} similarity=${dedupHit.similarity.toFixed(3)} status=${dedupHit.status}`,
      )
      return done(
        `这条记忆与已有记忆相似度 ${(dedupHit.similarity * 100).toFixed(0)}%，请先确认是否重复`,
        ["wechat-memory: dedup hit"],
      )
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
      // Conservative: 不 fallback 到 unscoped（与 /记忆 不同）—— candidate 不应该跨 project 泄露
      // /记忆 会 fallback 是因为 confirmed 数量通常稳定，unscoped 仍可控；
      // candidate 是待处理，不应让其他 project 的 pending 污染当前对话上下文。
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
    const tokenRaw = trimmed.slice("/确认记忆".length).trim()
    const candidates = await store.listBySubject({ subject, status: "candidate", limit: 20 })

    const legacyConfirm = async (record: (typeof candidates)[number] | undefined) => {
      if (!record) {
        return done("没有待确认的 candidate 记忆。", ["wechat-memory: confirm none"])
      }
      const updated = await store.update(confirmDurableMemory(record, Date.now()))
      return done(
        `已确认记忆 ${shortId(updated.id)}。`,
        [`wechat-memory: confirm ${updated.id}`],
      )
    }

    if (!tokenRaw.includes(",")) {
      // legacy: 无逗号 → 无参（最近 1 个，listBySubject 按 updatedAt desc，[0] 是最新）
      //                    OR 单 token（兼容旧用法，保留"已确认记忆 <shortId>。"格式）
      const target = tokenRaw
        ? candidates.find((c) => c.id === tokenRaw || shortId(c.id) === tokenRaw)
        : candidates[0]
      return legacyConfirm(target)
    }

    // batch: 逗号分隔 tokenRaw
    // 注：tokens 受 listBySubject limit=20 自然上限约束（按 updatedAt desc），
    //     超出范围 token 进 failed[] with "not found"。owner 想看全量先 /记忆候选。
    const tokens = Array.from(
      new Set(
        tokenRaw
          .split(",")
          .map((s) => s.trim())
          .filter((s) => s.length > 0),
      ),
    )
    if (tokens.length === 0) {
      // 仅逗号退化（如 `/确认记忆 ,`）：按无参处理，确认最近 1 个
      return legacyConfirm(candidates[0])
    }

    const targets: { readonly token: string; readonly record: (typeof candidates)[number] }[] = []
    const failed: { readonly token: string; readonly reason: string }[] = []
    for (const token of tokens) {
      const record = candidates.find((c) => c.id === token || shortId(c.id) === token)
      if (!record) {
        failed.push({ token, reason: "not found" })
        continue
      }
      targets.push({ token, record })
    }

    const confirmed: string[] = []
    // 注：不加 per-id try/catch（与 owner-routes handleBatch 不同）——
    //     wechat 是 owner 直连 channel，store.update 失败意味着 channel 全局
    //     异常，没必要 partial-success；abort + 让 caller 重试更直接。
    for (const { record } of targets) {
      const updated = await store.update(confirmDurableMemory(record, Date.now()))
      confirmed.push(shortId(updated.id))
    }

    const okLine =
      confirmed.length > 0 ? `已确认 ${confirmed.length} 条：${confirmed.join(", ")}` : null
    const failLine =
      failed.length > 0
        ? `失败 ${failed.length} 条：${failed.map((f) => `${f.token}=${f.reason}`).join(", ")}`
        : null
    const parts = [okLine, failLine].filter((p): p is string => p !== null)
    // 注：tokens.length===0 已在 line 133 early-return，targets/failed 至少一个非空 ⇒ summary 必非空。
    const summary = parts.join("；")
    return done(summary, [`wechat-memory: confirm-batch n=${confirmed.length} m=${failed.length}`])
  }

  return null
}
