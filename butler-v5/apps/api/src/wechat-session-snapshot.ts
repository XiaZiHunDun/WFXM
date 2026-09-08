/**
 * Capture the per-user session snapshot after every bot reply (B 方向 推 2).
 *
 * Query layer between the inbound handler and the on-disk state store:
 * - Counts open tasks for the user
 * - Counts pending candidate memories
 * - Determines `lastRunStatus` from the just-completed run's traces
 * - Persists via `writeWechatSessionState` (atomic write, file JSON)
 *
 * Pure I/O: never throws. Failure of any individual query degrades that
 * field to `null` rather than blocking the snapshot write. Owner-facing
 * surface is the digest builder, which renders `?` for `null`.
 */
import {
  writeWechatSessionState,
  type SessionRunStatus,
} from "./wechat-session-state.js"
import type { Wiring } from "./wiring.js"

/** Subset of ButlerLoopResult we actually inspect to derive run status. */
export type CaptureRunResult = {
  readonly traces: readonly string[]
  readonly finalDecision: string
}

const FAILURE_TRACE_PATTERNS: readonly RegExp[] = [
  /llm_call:error/,
  /conversation-loop:decode-fail/,
  /capability:error/,
  /delegate_to_subagent:error/,
  /:fail\b/,
  /\b500\b/,
]

function deriveLastRunStatus(runResult: CaptureRunResult | undefined): SessionRunStatus {
  if (!runResult) return "none"
  for (const t of runResult.traces) {
    for (const re of FAILURE_TRACE_PATTERNS) {
      if (re.test(t)) return "fail"
    }
  }
  return "success"
}

export async function captureWechatSessionSnapshot(args: {
  readonly wiring: Wiring
  readonly userId: string
  /** Pass the just-completed run result for LLM paths; omit for slash paths. */
  readonly runResult?: CaptureRunResult
  readonly env?: NodeJS.ProcessEnv
  readonly now?: number
}): Promise<void> {
  const env = args.env ?? process.env
  const userId = args.userId.trim()
  if (!userId) return

  let openTaskCount: number | null = null
  if (args.wiring.taskStore) {
    try {
      const items = await args.wiring.taskStore.listBySubject({
        subject: userId,
        status: "open",
        limit: 1000,
      })
      openTaskCount = items.length
    } catch {
      // keep null
    }
  }

  let candidateCount: number | null = null
  if (args.wiring.durableMemoryStore) {
    try {
      const items = await args.wiring.durableMemoryStore.listBySubject({
        subject: userId,
        status: "candidate",
        limit: 1000,
      })
      candidateCount = items.length
    } catch {
      // keep null
    }
  }

  const lastRunStatus = deriveLastRunStatus(args.runResult)

  writeWechatSessionState(
    userId,
    {
      openTaskCount,
      candidateCount,
      lastRunStatus,
      lastReplyAt: args.now ?? Date.now(),
    },
    env,
  )
}
