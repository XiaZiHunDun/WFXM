/**
 * Time-boxed dev session grants: batch-approve run_command + write_file
 * for a subject without per-call WeChat confirmation.
 *
 * Grants are persisted in scoped_grants (P1 unified Policy path) on a
 * synthetic dev-session Run anchor per owner subject.
 */
import { createHash } from "node:crypto"
import type { RuntimeStore } from "@butler/domain/runtime.js"
import { issuePreconfiguredGrants } from "@butler/runtime/scoped-grant-service.js"
import { resolveOwnerSubject } from "./tool-boundary.js"

export const DEV_SESSION_TOOLS = ["run_command", "write_file"] as const

const DEFAULT_TTL_MINUTES = 30
const DEFAULT_MAX_USES = 50

/** Deterministic pseudo-run id for dev session grants (valid UUID). */
export function devSessionRunId(subject: string): string {
  const digest = createHash("sha256")
    .update(`butler-v5-dev-session:${subject.trim()}`)
    .digest("hex")
  return [
    digest.slice(0, 8),
    digest.slice(8, 12),
    `4${digest.slice(13, 16)}`,
    `8${digest.slice(17, 20)}`,
    digest.slice(20, 32),
  ].join("-")
}

export function devSessionConversationId(subject: string): string {
  return `c-dev-session-${subject.trim()}`
}

export function isDevSessionPhrase(content: string): boolean {
  const t = content.trim().toLowerCase()
  if (t === "/开发模式" || t === "/dev" || t === "/dev mode") return true
  return (
    t.includes("开发模式") ||
    t.includes("进入开发") ||
    t === "dev mode" ||
    t.startsWith("开启开发")
  )
}

export function devSessionTtlMs(env: NodeJS.ProcessEnv = process.env): number {
  const raw = Number(env["BUTLER_V5_DEV_SESSION_GRANT_MINUTES"] ?? DEFAULT_TTL_MINUTES)
  const minutes = Number.isFinite(raw) && raw > 0 ? raw : DEFAULT_TTL_MINUTES
  return minutes * 60 * 1000
}

export function devSessionMaxUses(env: NodeJS.ProcessEnv = process.env): number {
  const raw = Number(env["BUTLER_V5_DEV_SESSION_MAX_USES"] ?? DEFAULT_MAX_USES)
  return Number.isFinite(raw) && raw > 0 ? Math.floor(raw) : DEFAULT_MAX_USES
}

async function ensureDevSessionAnchorRun(args: {
  readonly store: RuntimeStore
  readonly ownerSubject: string
  readonly createdAt: Date
}): Promise<string> {
  const conversationId = devSessionConversationId(args.ownerSubject)
  const runId = devSessionRunId(args.ownerSubject)
  await args.store.createConversationWithUserMessage({
    conversationId,
    messageId: crypto.randomUUID(),
    subject: args.ownerSubject,
    content: { text: "[dev-session-anchor]" },
    triggerSource: "api",
    idempotencyKey: `dev-session-conv:${args.ownerSubject}`,
    createdAt: args.createdAt,
  })
  await args.store.createRun({
    id: runId,
    conversationId,
    parentRunId: null,
    triggerSource: "api",
    idempotencyKey: `dev-session-run:${args.ownerSubject}`,
    subject: args.ownerSubject,
    goal: "dev-session-grant-anchor",
    budget: { maxSteps: 0 },
    deadline: null,
    createdAt: args.createdAt,
  })
  return runId
}

export async function ensureDevSessionGrants(args: {
  readonly store: RuntimeStore
  readonly subject: string
  readonly env?: NodeJS.ProcessEnv
}): Promise<{ readonly expiresAt: Date; readonly maxUses: number }> {
  const env = args.env ?? process.env
  const ownerSubject = resolveOwnerSubject(env, args.subject)
  const now = new Date()
  const ttlMs = devSessionTtlMs(env)
  const maxUses = devSessionMaxUses(env)
  const runId = await ensureDevSessionAnchorRun({
    store: args.store,
    ownerSubject,
    createdAt: now,
  })
  await issuePreconfiguredGrants({
    store: args.store,
    runId,
    subject: ownerSubject,
    capabilities: DEV_SESSION_TOOLS,
    maxUses,
    ttlMs,
    refreshExisting: true,
    createdAt: now,
  })
  return { expiresAt: new Date(now.getTime() + ttlMs), maxUses }
}

export function formatDevSessionEnabledReply(args: {
  readonly expiresAt: Date
  readonly maxUses: number
}): string {
  const until = args.expiresAt.toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })
  return [
    `✅ 开发模式已开启（至 ${until}）`,
    `本时段内 run_command / write_file 最多 ${args.maxUses} 次，无需逐条确认。`,
    "发送开发任务即可；回复 /状态 查看项目概况。",
  ].join("\n")
}
