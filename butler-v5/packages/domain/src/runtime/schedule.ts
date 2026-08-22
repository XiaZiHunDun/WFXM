/**
 * Heartbeat / Schedule — pure Trigger math only.
 * Schedule never owns a second Run Engine, Policy, or Workflow.
 */

import type { RunTrigger } from "./types.js"
import { buildRunTrigger } from "./run-trigger.js"

/** Default subject for Schedule-created Runs (DESIGN §11). */
export const SCHEDULE_SUBJECT = "system:scheduler" as const

/** First-cut Schedule jobs are read-only / low-risk by default. */
export const SCHEDULE_SAFE_TOOL_NAMES: readonly string[] = [
  "recall_history",
  "recall_durable_memory",
  "recall_document",
  "get_current_time",
  "greet_with_time",
  "summarize_today",
  "read_file",
]

export interface ScheduleJobSpec {
  readonly id: string
  /** Interval between intended fires (ms). */
  readonly everyMs: number
  /** Goal text injected as the Run user message. */
  readonly goal: string
  /** Conversation that owns this job's main Run (defaults to schedule-{id}). */
  readonly conversationId?: string
  /** Minimum gap after a successful or deferred fire attempt. */
  readonly cooldownMs: number
  readonly maxSteps: number
  /** Wall-clock budget for the Run; null = no deadline. */
  readonly deadlineMs: number | null
  /** When true, empty / "ok" / "quiet" replies are success without fanfare. */
  readonly quietSuccess: boolean
  readonly enabled: boolean
}

export type ScheduleTickDecision =
  | { readonly _tag: "skip"; readonly reason: string }
  | { readonly _tag: "defer"; readonly reason: string }
  | {
      readonly _tag: "fire"
      readonly job: ScheduleJobSpec
      readonly conversationId: string
      readonly idempotencyKey: string
      readonly windowStartMs: number
      readonly deadline: Date | null
    }

export function defaultScheduleConversationId(jobId: string): string {
  return `schedule-${jobId.trim()}`
}

export function scheduleWindowStartMs(nowMs: number, everyMs: number): number {
  if (everyMs <= 0) return nowMs
  return Math.floor(nowMs / everyMs) * everyMs
}

export function scheduleIdempotencyKey(jobId: string, windowStartMs: number): string {
  return `schedule:${jobId.trim()}:${windowStartMs}`
}

export function buildScheduleRunTrigger(input: {
  readonly jobId: string
  readonly goal: string
  readonly conversationId: string
  readonly idempotencyKey: string
  readonly everyMs: number
  readonly quietSuccess?: boolean
}): RunTrigger {
  return buildRunTrigger({
    subject: SCHEDULE_SUBJECT,
    source: "schedule",
    conversationRef: input.conversationId,
    payload: {
      jobId: input.jobId,
      goal: input.goal,
      everyMs: input.everyMs,
      quietSuccess: input.quietSuccess ?? true,
    },
    trustLevel: "trusted",
    idempotencyKey: input.idempotencyKey,
  })
}

export function isQuietScheduleReply(reply: string, quietSuccess: boolean): boolean {
  if (!quietSuccess) return false
  const text = reply.trim().toLowerCase()
  if (text.length === 0) return true
  return (
    text === "ok" ||
    text === "quiet" ||
    text === "noop" ||
    text === "无事" ||
    text === "无异常" ||
    text.startsWith("quiet:")
  )
}

export interface ScheduleTickInput {
  readonly job: ScheduleJobSpec
  readonly nowMs: number
  /** Last completed fire / defer attempt for this job (ms), if any. */
  readonly lastAttemptMs: number | null
  /** True when this conversation already has an active main Run. */
  readonly conversationBusy: boolean
  /** True when the delivery shell reports the main queue is busy. */
  readonly mainQueueBusy: boolean
  /** True when another schedule job is currently executing in-process. */
  readonly scheduleInFlight: boolean
}

/**
 * Decide whether a job should fire, defer, or skip on this tick.
 */
export function evaluateScheduleTick(input: ScheduleTickInput): ScheduleTickDecision {
  const { job, nowMs } = input
  if (!job.enabled) return { _tag: "skip", reason: "disabled" }
  if (!job.id.trim()) return { _tag: "skip", reason: "empty job id" }
  if (!job.goal.trim()) return { _tag: "skip", reason: "empty goal" }
  if (job.everyMs <= 0) return { _tag: "skip", reason: "everyMs must be > 0" }

  if (input.lastAttemptMs !== null && nowMs - input.lastAttemptMs < job.cooldownMs) {
    return { _tag: "skip", reason: "cooldown" }
  }

  const windowStartMs = scheduleWindowStartMs(nowMs, job.everyMs)
  if (input.lastAttemptMs !== null && input.lastAttemptMs >= windowStartMs) {
    return { _tag: "skip", reason: "already fired this window" }
  }

  if (input.scheduleInFlight) {
    return { _tag: "defer", reason: "schedule in flight" }
  }
  if (input.mainQueueBusy) {
    return { _tag: "defer", reason: "main queue busy" }
  }
  if (input.conversationBusy) {
    return { _tag: "defer", reason: "conversation busy" }
  }

  const conversationId = job.conversationId?.trim() || defaultScheduleConversationId(job.id)
  const deadline =
    job.deadlineMs !== null && job.deadlineMs > 0 ? new Date(nowMs + job.deadlineMs) : null

  return {
    _tag: "fire",
    job,
    conversationId,
    idempotencyKey: scheduleIdempotencyKey(job.id, windowStartMs),
    windowStartMs,
    deadline,
  }
}
