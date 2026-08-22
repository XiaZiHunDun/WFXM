import {
  SCHEDULE_SAFE_TOOL_NAMES,
  SCHEDULE_SUBJECT,
  buildScheduleRunTrigger,
  isQuietScheduleReply,
  validateRunTrigger,
  type ScheduleJobSpec,
} from "@butler/domain/runtime.js"
import { runButlerLoop, type ButlerLoopResult } from "./wechat-inbound-butler.js"
import type { Wiring } from "./wiring.js"

export interface ScheduleFireInput {
  readonly wiring: Wiring
  readonly job: ScheduleJobSpec
  readonly conversationId: string
  readonly idempotencyKey: string
  readonly deadline: Date | null
  readonly env?: NodeJS.ProcessEnv
}

export interface ScheduleFireResult {
  readonly loop: ButlerLoopResult
  readonly quiet: boolean
}

/**
 * Fire one Schedule job as an isolated RunTrigger → RunEngine loop.
 * Uses read-only tool allowlist; side effects still require ScopedGrant via Policy.
 */
export async function runScheduleJob(input: ScheduleFireInput): Promise<ScheduleFireResult> {
  const env = input.env ?? process.env
  const trigger = buildScheduleRunTrigger({
    jobId: input.job.id,
    goal: input.job.goal,
    conversationId: input.conversationId,
    idempotencyKey: input.idempotencyKey,
    everyMs: input.job.everyMs,
    quietSuccess: input.job.quietSuccess,
  })
  const validated = validateRunTrigger(trigger)
  if (!validated.ok) {
    throw new Error(`invalid Schedule RunTrigger: ${validated.reason}`)
  }

  const loop = await runButlerLoop({
    wiring: input.wiring,
    conversationId: input.conversationId,
    content: input.job.goal,
    fromUserId: SCHEDULE_SUBJECT,
    projectId: "schedule",
    idempotencyKey: input.idempotencyKey,
    runTrigger: trigger,
    goal: input.job.goal,
    budget: { maxSteps: input.job.maxSteps },
    deadline: input.deadline,
    allowedToolNames: SCHEDULE_SAFE_TOOL_NAMES,
    env,
  })

  return {
    loop,
    quiet: isQuietScheduleReply(loop.reply, input.job.quietSuccess),
  }
}
