/**
 * Combined "task digest" reply for the `task_digest` intent.
 *
 * Owner is on WeChat (low-frequency interaction). Instead of forcing them
 * to type /状态 + /待办 + /记忆候选 one after another, a free-form
 * "我刚才在干啥" / "现在啥状态" / "还有什么" routes here and returns
 * a single message composed of three on-demand digests in parallel.
 *
 * Zero LLM cost: this is a pure data fan-out over the same backing stores
 * the slash commands use. The three sub-digest helpers are the same ones
 * `/状态` / `/待办` / `/记忆候选` already call, so per-section wording
 * stays in lockstep with the slash commands.
 */
import type { McpToolBundle } from "./mcp-bootstrap.js"
import type { ButlerLoopResult } from "./wechat-inbound-butler.js"
import type { Wiring } from "./wiring.js"
import { formatStatusDigest } from "./wechat-project-surface.js"
import { formatOpenTasksDigest } from "./wechat-task-commands.js"
import { formatMemoryCandidatesDigest } from "./wechat-memory-commands.js"
import { getWechatActiveProjectId } from "./wechat-active-project.js"
import { resolveWechatProjectLabel } from "./wechat-active-project.js"

/** Defensive cap; WeChat supports ~4000 chars but 1500 keeps replies
 *  scannable on mobile and matches the owner-set budget for this surface. */
const DIGEST_MAX_CHARS = 1500

const TRUNCATION_NOTE = "\n\n（…摘要过长，详见 /状态 · /待办 · /记忆候选）"

const FAILURE_FALLBACK = {
  status: "项目状态查询失败，请稍后重试。",
  tasks: "待办查询失败，请稍后重试。",
  candidates: "记忆候选查询失败，请稍后重试。",
} as const

export async function formatTaskDigestReply(args: {
  readonly wiring: Wiring
  readonly fromUserId: string
  readonly env?: NodeJS.ProcessEnv
  readonly mcpBundle?: McpToolBundle
}): Promise<ButlerLoopResult> {
  const env = args.env ?? process.env
  const subject = args.fromUserId.trim()
  const active = getWechatActiveProjectId(subject, env)
  // D59 T2 (audit #3 F-09): surface owner-facing label (e.g. "WFXM") in
  // digest section headings rather than the raw internal id. Falls back
  // to the raw id when no catalog entry exists for the project id.
  const ownerLabel = resolveWechatProjectLabel(active, env)

  // Parallel fetch with fault isolation: a single section's failure must
  // not blank the whole digest. allSettled lets us render the other two
  // segments even if one store throws.
  const settled = await Promise.allSettled([
    formatStatusDigest({
      wiring: args.wiring,
      fromUserId: args.fromUserId,
      env,
      ...(args.mcpBundle === undefined ? {} : { mcpBundle: args.mcpBundle }),
    }),
    formatOpenTasksDigest(
      { wiring: args.wiring, fromUserId: args.fromUserId, env },
      { emptyMessage: "暂无开放待办。" },
    ),
    formatMemoryCandidatesDigest(
      { wiring: args.wiring, fromUserId: args.fromUserId, env },
      { emptyMessage: "暂无待审记忆。" },
    ),
  ])

  // formatStatusDigest returns `Promise<string>` directly, while
  // formatOpenTasksDigest / formatMemoryCandidatesDigest return
  // `{ text, isEmpty }`. Unwrap each according to its actual shape.
  // D60 T2.2 (audit #3 F-06): drop raw error reason from owner-facing
  // failure text. The per-backend distinction comes from FAILURE_FALLBACK's
  // distinct base messages ("项目状态查询失败" / "待办查询失败" / "记忆候选查询失败"),
  // so owners can still tell which backend is degraded without seeing
  // internals like 'connection refused on 127.0.0.1:5432'.
  // (D55 SF-01 wanted per-backend distinction; that's preserved.)
  // The raw reason is kept in `reasonTrace` below for operator observability.
  const reasonOf = (s: PromiseSettledResult<unknown>): string | null =>
    s.status === "rejected"
      ? s.reason instanceof Error
        ? s.reason.message
        : String(s.reason)
      : null
  const statusReason = reasonOf(settled[0])
  const tasksReason = reasonOf(settled[1])
  const candidatesReason = reasonOf(settled[2])
  const statusText =
    settled[0].status === "fulfilled" ? settled[0].value : FAILURE_FALLBACK.status
  const tasksText =
    settled[1].status === "fulfilled" ? settled[1].value.text : FAILURE_FALLBACK.tasks
  const candidatesText =
    settled[2].status === "fulfilled"
      ? settled[2].value.text
      : FAILURE_FALLBACK.candidates
  const failedCount =
    (settled[0].status === "rejected" ? 1 : 0) +
    (settled[1].status === "rejected" ? 1 : 0) +
    (settled[2].status === "rejected" ? 1 : 0)
  const reasonTrace =
    failedCount > 0
      ? `task-digest:reason=${[
          statusReason ? `status=${statusReason}` : null,
          tasksReason ? `tasks=${tasksReason}` : null,
          candidatesReason ? `candidates=${candidatesReason}` : null,
        ]
          .filter((s): s is string => s !== null)
          .join("; ")}`
      : null

  const body = [
    `【任务摘要 · ${ownerLabel}】`,
    "",
    "【项目状态】",
    statusText,
    "",
    `【开放待办】（${ownerLabel}）`,
    tasksText,
    "",
    `【候选记忆】（${ownerLabel}）`,
    candidatesText,
    "",
    "——",
    "如需详情：/状态 · /待办 · /记忆候选",
  ].join("\n")

  const reply =
    body.length > DIGEST_MAX_CHARS
      ? body.slice(0, DIGEST_MAX_CHARS - TRUNCATION_NOTE.length) + TRUNCATION_NOTE
      : body

  return {
    reply,
    iterations: 0,
    toolCalls: 0,
    finalDecision: "Respond",
    traces: [
      "intake:task_digest",
      `task-digest:active=${active}`,
      `task-digest:failed=${failedCount}`,
      ...(reasonTrace === null ? [] : [reasonTrace]),
    ],
  }
}
