import { buildCliRunTrigger, validateRunTrigger } from "@butler/domain/runtime.js"
import { runButlerLoop, type ButlerLoopResult } from "./wechat-inbound-butler.js"
import { resolveOwnerSubject } from "./tool-boundary-helpers.js"
import type { Wiring } from "./wiring.js"

/**
 * D64 T3 (audit #9 F-04 cross-channel wiring): CLI inbound inherits the
 * approval-fatigue mitigation wired inside `runButlerLoop` (which
 * dispatches `channel: "cli"` when projectId="cli"). Cooldown is applied
 * inline (CLI is interactive, owner sees logs); checklist prompts
 * surface via the existing RunPauseForApproval flow.
 *
 * This file is intentionally a thin shim — wiring is centralized at the
 * `runButlerLoop` chokepoint so wechat / telegram / cli all share the
 * same fatigue policy without per-channel drift.
 */
export function defaultCliConversationId(subject: string, goal: string): string {
  const slug = Buffer.from(goal, "utf8").toString("base64url").slice(0, 16)
  return `cli-${subject}-${slug}`
}

export async function runCliGoal(args: {
  readonly wiring: Wiring
  readonly goal: string
  readonly subject?: string
  readonly conversationId?: string
  readonly env?: NodeJS.ProcessEnv
}): Promise<ButlerLoopResult> {
  const env = args.env ?? process.env
  const subject = args.subject ?? resolveOwnerSubject(env, "cli-owner")
  const idempotencyKey = `cli-${Date.now()}`
  const trigger = buildCliRunTrigger({
    subject,
    goal: args.goal,
    idempotencyKey,
  })
  const validated = validateRunTrigger(trigger)
  if (!validated.ok) {
    throw new Error(`invalid RunTrigger: ${validated.reason}`)
  }
  const conversationId = args.conversationId ?? defaultCliConversationId(subject, args.goal)
  return runButlerLoop({
    wiring: args.wiring,
    conversationId,
    content: args.goal,
    fromUserId: subject,
    projectId: "cli",
    idempotencyKey,
    runTrigger: trigger,
    env,
  })
}
