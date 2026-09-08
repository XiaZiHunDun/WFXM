/**
 * Session-open digest: when owner opens a wechat session after a long
 * idle, prepend a one-line "since you were last here" digest to the
 * bot's first reply.
 *
 * - Reads the last snapshot via `readWechatSessionState`.
 * - If the snapshot is older than `BUTLER_V5_SESSION_DIGEST_IDLE_MS`
 *   (default 30 min), returns a digest line. Otherwise returns null.
 * - Pure function: no I/O, no LLM. The caller (routes.ts or
 *   wechat-inbound-butler.ts) decides whether and where to prepend.
 *
 * Owner-facing format: "【上次您离开时】(约 Nm 前) · 3 任务在跑 · 5 候选待审 · 0 失败"
 * Concise by design — owners on wechat want a glance, not a paragraph.
 */
import { readWechatSessionState, type SessionState } from "./wechat-session-state.js"

const DEFAULT_IDLE_MS = 30 * 60 * 1000 // 30 min

export function sessionDigestIdleMs(env: NodeJS.ProcessEnv = process.env): number {
  const raw = env["BUTLER_V5_SESSION_DIGEST_IDLE_MS"]?.trim()
  if (!raw) return DEFAULT_IDLE_MS
  const n = Number(raw)
  if (!Number.isFinite(n) || n < 0) return DEFAULT_IDLE_MS
  return n
}

export type SessionDigest = {
  readonly text: string
  readonly minutesSinceLastReply: number
  readonly state: SessionState
}

function formatElapsed(ms: number): string {
  const minutes = Math.floor(ms / 60_000)
  if (minutes < 1) return "刚刚"
  if (minutes < 60) return `${minutes}m 前`
  if (minutes < 60 * 24) return `${Math.floor(minutes / 60)}h 前`
  return `${Math.floor(minutes / (60 * 24))}d 前`
}

function formatCount(n: number | null): string {
  return n === null ? "?" : String(n)
}

export function buildSessionOpenDigest(args: {
  readonly userId: string
  readonly now: number
  readonly env?: NodeJS.ProcessEnv
}): SessionDigest | null {
  const env = args.env ?? process.env
  const idleMs = sessionDigestIdleMs(env)
  const state = readWechatSessionState(args.userId, env)
  if (!state) return null
  const elapsed = args.now - state.lastReplyAt
  if (elapsed < idleMs) return null

  const failedRuns = state.lastRunStatus === "fail" ? 1 : 0
  const text =
    `【上次您离开时】(约 ${formatElapsed(elapsed)}) · ` +
    `${formatCount(state.openTaskCount)} 任务在跑 · ` +
    `${formatCount(state.candidateCount)} 候选待审 · ` +
    `${failedRuns} 失败`

  return {
    text,
    minutesSinceLastReply: Math.floor(elapsed / 60_000),
    state,
  }
}

/**
 * Convenience wrapper for the inbound reply path: build the digest (if
 * applicable) and prepend it to the bot's reply. Extracted so the prepend
 * logic is independently testable without spinning up the full route.
 */
export function maybePrependSessionDigest(args: {
  readonly reply: string
  readonly userId: string
  readonly now: number
  readonly env?: NodeJS.ProcessEnv
}): { readonly reply: string; readonly digest: SessionDigest | null } {
  const env = args.env ?? process.env
  const digest = buildSessionOpenDigest({ userId: args.userId, now: args.now, env })
  if (!digest) return { reply: args.reply, digest: null }
  return {
    reply: `${digest.text}\n\n${args.reply}`,
    digest,
  }
}
