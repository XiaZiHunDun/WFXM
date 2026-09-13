/**
 * Sweeper → WeChat proactive push (C 方向 推 3).
 *
 * Lets the opt-in background sweepers (D40 candidate expires, D42
 * auto-promote) ping the owner via wechat when they actually do work,
 * without spamming: 1h per (owner, sweeper-type) in-memory throttle, so
 * a noisy sweep loop emits at most one push per hour per type.
 *
 * Default OFF — owner must opt in via `BUTLER_V5_SWEEPER_NOTIFY_ENABLED=1`
 * and pick the recipient via `BUTLER_V5_SWEEPER_NOTIFY_OWNER=<userId>`.
 * The push reuses `sendWechatProactiveNotify` (ChannelPort → ilink → mock
 * outbox) so no new outbound path is introduced.
 */
import type { ChannelKind, ChannelPort } from "@butler/ports/core/channel.js"
import { envTruthy } from "./env-util.js"
import { describeEnvKnob } from "./owner-jargon.js"
import { sendWechatProactiveNotify } from "./wechat-run-notify.js"

type SweeperType = "candidate_expires" | "auto_promote"

const DEFAULT_THROTTLE_MS = 60 * 60 * 1000 // 1 hour

export function sweeperNotifyThrottleMs(env: NodeJS.ProcessEnv = process.env): number {
  const raw = env["BUTLER_V5_SWEEPER_NOTIFY_THROTTLE_MS"]?.trim()
  if (!raw) return DEFAULT_THROTTLE_MS
  const n = Number(raw)
  if (!Number.isFinite(n) || n < 0) return DEFAULT_THROTTLE_MS
  return n
}

export function isSweeperNotifyEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return envTruthy(env["BUTLER_V5_SWEEPER_NOTIFY_ENABLED"])
}

export function resolveSweeperNotifyOwner(env: NodeJS.ProcessEnv = process.env): string | null {
  const owner = (env["BUTLER_V5_SWEEPER_NOTIFY_OWNER"] ?? "").trim()
  return owner || null
}

export function formatCandidateExpiresNotify(input: {
  readonly expired: number
  readonly scanned: number
}): string {
  if (input.expired <= 0) return ""
  return [
    `【候选过期清理】${input.expired} 条候选已自动过期（扫描 ${input.scanned} 条）。`,
    `查看 /记忆候选，或调整 ${describeEnvKnob("BUTLER_V5_CANDIDATE_EXPIRES_TTL_MS")}。`,
  ].join("\n")
}

export function formatAutoPromoteNotify(input: {
  readonly promoted: number
  readonly scanned: number
}): string {
  if (input.promoted <= 0) return ""
  return [
    `【候选自动升级】${input.promoted} 条候选已自动升级为 confirmed（扫描 ${input.scanned} 条）。`,
    "查看 /记忆；如有疑问请回复「撤销刚才」。",
  ].join("\n")
}

// In-memory throttle state. Per process; lost on restart, which is fine
// because the next push after restart will be at most 1h after a real
// sweep, and the owner can always re-trigger via /记忆候选.
const lastSentAtMs = new Map<string, number>()

export function resetSweeperThrottleForTests(): void {
  lastSentAtMs.clear()
}

export function _peekSweeperThrottleForTests(key: string): number | undefined {
  return lastSentAtMs.get(key)
}

export type PushSweeperNotifyDeps = {
  readonly type: SweeperType
  readonly to: string
  readonly text: string
  readonly env: NodeJS.ProcessEnv
  readonly channels?: ReadonlyMap<ChannelKind, ChannelPort>
  readonly now?: number
  readonly throttleMs?: number
  readonly send?: typeof sendWechatProactiveNotify
}

export type PushSweeperNotifyResult =
  | { readonly sent: true }
  | { readonly sent: false; readonly reason: string }

export async function pushSweeperNotify(
  args: PushSweeperNotifyDeps,
): Promise<PushSweeperNotifyResult> {
  if (!args.text) return { sent: false, reason: "empty text" }
  if (!isSweeperNotifyEnabled(args.env)) return { sent: false, reason: "disabled" }
  const to = args.to.trim()
  if (!to) return { sent: false, reason: "no owner" }

  const now = args.now ?? Date.now()
  const throttleMs = args.throttleMs ?? sweeperNotifyThrottleMs(args.env)
  const key = `${args.type}:${to}`
  const last = lastSentAtMs.get(key)
  if (last !== undefined && now - last < throttleMs) {
    return { sent: false, reason: "throttled" }
  }

  const send = args.send ?? sendWechatProactiveNotify
  let result: { readonly ok: true } | { readonly ok: false; readonly reason: string }
  try {
    result = await send({
      to,
      text: args.text,
      env: args.env,
      ...(args.channels === undefined ? {} : { channels: args.channels }),
    })
  } catch (err) {
    // D55 SF-04: throttle on failure too — persistent errors (ilink down,
    // misconfigured token) would otherwise spam every sweeper tick. Owner
    // can still bypass via /记忆候选 command path which is not throttled.
    lastSentAtMs.set(key, now)
    return {
      sent: false,
      reason: err instanceof Error ? err.message : String(err),
    }
  }
  // Record throttle regardless of ok/fail — same rationale as the throw
  // path above: a non-ok result is still an attempted push that consumed
  // the window, and the next tick shouldn't burn through the same outage.
  lastSentAtMs.set(key, now)
  if (!result.ok) return { sent: false, reason: result.reason }
  return { sent: true }
}
