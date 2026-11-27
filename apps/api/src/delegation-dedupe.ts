/**
 * F31: delegation dedupe guard.
 *
 * Symptom (Phase 7 batch V): the parent butler re-delegated a task that had
 * already been delivered in the same conversation. The conversation history
 * is compacted (newest ~12 messages / 4000 chars), so the older "task done"
 * reply fell out of context while the older user spec stayed in, and the
 * model merged both into "two tasks to start".
 *
 * The audit log already records every delegation and completion with
 * `parentConversationId` + `task`, so we can block near-identical re-runs
 * deterministically instead of relying on the model to remember.
 *
 * Design:
 *   - Pure helpers (`normalizeTaskText` / `taskSimilarity` /
 *     `findCompletedDuplicateInAudit`) are unit-testable without touching
 *     the filesystem.
 *   - `findRecentlyCompletedDuplicate` reads only a bounded tail of the
 *     JSONL audit log (it can be tens of MB).
 *   - Explicit rework intent (返工/修复/重做/…) bypasses the guard, so
 *     legitimate follow-up fixes still work.
 */
import { readRecentSubagentAuditTail, type AuditEntry } from "./audit-log.js"

export interface CompletedDuplicate {
  /** The task text of the already-completed delegation. */
  readonly task: string
  readonly childConversationId: string
  readonly similarity: number
  /** ISO timestamp of the completed delegation. */
  readonly completedAt: string
}

const TASK_NORMALIZE_MAX = 600
const DEDUPE_WINDOW_MS = 24 * 60 * 60 * 1000
const DEFAULT_THRESHOLD = 0.45
const MIN_TASK_CHARS = 12
/** Explicit "do it again / fix it" wording means the owner really wants a rerun. */
const REWORK_INTENT =
  /(返工|重做|重新做|重新实现|再改|修复|修正|回滚|撤销|继续上次|接着上次|重跑)/u

export function isDelegationDedupeEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  const raw = (env["BUTLER_V5_DELEGATION_DEDUPE"] ?? "1").trim().toLowerCase()
  return raw !== "0" && raw !== "false" && raw !== "off"
}

export function resolveDedupeThreshold(env: NodeJS.ProcessEnv = process.env): number {
  const rawText = (env["BUTLER_V5_DELEGATION_DEDUPE_THRESHOLD"] ?? "").trim()
  if (rawText === "") return DEFAULT_THRESHOLD
  const raw = Number(rawText)
  if (!Number.isFinite(raw)) return DEFAULT_THRESHOLD
  return Math.min(0.95, Math.max(0.3, raw))
}

/** Collapse whitespace and bound length so similarity is cheap and stable. */
export function normalizeTaskText(text: string): string {
  return text.replace(/\s+/gu, " ").trim().slice(0, TASK_NORMALIZE_MAX)
}

function tokenSet(text: string): Set<string> {
  const tokens = text.match(/[A-Za-z0-9_./-]{2,}|[\u4e00-\u9fff]{2,}/gu) ?? []
  return new Set(tokens.map((token) => token.toLowerCase()))
}

function letterBigrams(text: string): Set<string> {
  const chars = Array.from(text.toLowerCase()).filter((ch) => /[\p{L}\p{N}]/u.test(ch))
  const grams = new Set<string>()
  for (let i = 0; i < chars.length - 1; i += 1) {
    grams.add(`${chars[i]}${chars[i + 1]}`)
  }
  return grams
}

function jaccard(a: Set<string>, b: Set<string>): number {
  if (a.size === 0 || b.size === 0) return 0
  let shared = 0
  for (const item of a) {
    if (b.has(item)) shared += 1
  }
  return shared / (a.size + b.size - shared)
}

/**
 * 0..1 similarity.
 *
 * Character-level Levenshtein alone was not enough: the real replay in batch V
 * was reworded ("在 LingWen 仓库（…）实现…" vs "在 LingWen（工作区根即…）实现…")
 * and scored only 0.74, below any safe threshold. Token overlap (feature
 * keywords, file paths) plus character bigrams separates that pair (0.48 /
 * 0.58) from unrelated tasks in the same repo (≤0.25 / 0.35).
 */
export function taskSimilarity(a: string, b: string): number {
  const x = normalizeTaskText(a)
  const y = normalizeTaskText(b)
  if (x === "" && y === "") return 1
  if (x === "" || y === "") return 0
  if (x === y) return 1
  return Math.max(jaccard(tokenSet(x), tokenSet(y)), jaccard(letterBigrams(x), letterBigrams(y)))
}

/**
 * Find a delegation in `entries` that (a) belongs to the same parent
 * conversation, (b) has a completion row, and (c) is near-identical to
 * `task`. Returns the best match above the threshold, else undefined.
 */
export function findCompletedDuplicateInAudit(args: {
  readonly task: string
  readonly parentConversationId: string
  readonly entries: readonly AuditEntry[]
  readonly env?: NodeJS.ProcessEnv
  readonly nowMs?: number
}): CompletedDuplicate | undefined {
  const env = args.env ?? process.env
  if (!isDelegationDedupeEnabled(env)) return undefined
  const taskText = normalizeTaskText(args.task)
  if (taskText.length < MIN_TASK_CHARS) return undefined
  if (REWORK_INTENT.test(taskText)) return undefined
  const threshold = resolveDedupeThreshold(env)
  const now = args.nowMs ?? Date.now()
  const completedChildren = new Set(
    args.entries
      .filter((entry) => entry.kind === "completion" && entry.childConversationId)
      .map((entry) => entry.childConversationId),
  )
  let best: CompletedDuplicate | undefined
  for (const entry of args.entries) {
    if (entry.kind !== "delegation") continue
    if (entry.parentConversationId !== args.parentConversationId) continue
    if (!entry.childConversationId || !completedChildren.has(entry.childConversationId)) continue
    const ts = Date.parse(entry.ts)
    if (Number.isFinite(ts) && now - ts > DEDUPE_WINDOW_MS) continue
    const similarity = taskSimilarity(taskText, entry.task)
    if (similarity < threshold) continue
    if (best === undefined || similarity > best.similarity) {
      best = {
        task: entry.task,
        childConversationId: entry.childConversationId,
        similarity,
        completedAt: entry.ts,
      }
    }
  }
  return best
}

/** Production entry: reads a bounded audit tail, then applies the pure check. */
export function findRecentlyCompletedDuplicate(args: {
  readonly task: string
  readonly parentConversationId: string
  readonly env?: NodeJS.ProcessEnv
  readonly nowMs?: number
}): CompletedDuplicate | undefined {
  const env = args.env ?? process.env
  if (!isDelegationDedupeEnabled(env)) return undefined
  const entries = readRecentSubagentAuditTail(200, env)
  return findCompletedDuplicateInAudit({
    task: args.task,
    parentConversationId: args.parentConversationId,
    entries,
    env,
    ...(args.nowMs === undefined ? {} : { nowMs: args.nowMs }),
  })
}

/** Owner-facing rejection text. */
export function formatDuplicateRejection(dup: CompletedDuplicate): string {
  const percent = Math.round(dup.similarity * 100)
  return [
    `已阻止重复派发：该任务与上一轮已完成的任务相似度 ${percent}%，且那次已经交付过。`,
    "不要原样重发；如果确实需要返工，请在 task 中写明新的修改点（或包含「修复/返工」字样），否则直接向 owner 汇报即可。",
  ].join("")
}
