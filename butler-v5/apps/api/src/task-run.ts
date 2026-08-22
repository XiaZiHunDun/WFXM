import {
  advanceTaskAfterStep,
  defaultTaskConversationId,
  resolveTaskRunGoal,
  type TaskRecord,
} from "@butler/domain/knowledge/task-procedure.js"
import {
  buildTaskRunTrigger,
  validateRunTrigger,
} from "@butler/domain/runtime.js"
import { runButlerLoop, type ButlerLoopResult } from "./wechat-inbound-butler.js"
import type { Wiring } from "./wiring.js"

export async function runTaskGoal(args: {
  readonly wiring: Wiring
  readonly taskId: string
  readonly advance?: boolean
  readonly env?: NodeJS.ProcessEnv
}): Promise<{
  readonly task: TaskRecord
  readonly loop: ButlerLoopResult
  readonly goal: string
  readonly stepKey: string | null
}> {
  const env = args.env ?? process.env
  const tasks = args.wiring.taskStore
  const procedures = args.wiring.procedureStore
  if (!tasks) throw new Error("task store unavailable")

  const task = await tasks.get(args.taskId)
  if (!task) throw new Error(`task not found: ${args.taskId}`)

  const procedure =
    task.procedureId && procedures ? await procedures.get(task.procedureId) : null
  const resolved = resolveTaskRunGoal(task, procedure)
  if (!resolved.ok) throw new Error(resolved.reason)

  const conversationId = task.conversationId ?? defaultTaskConversationId(task.id)
  const idempotencyKey = `task:${task.id}:${Date.now()}`
  const trigger = buildTaskRunTrigger({
    subject: task.subject,
    taskId: task.id,
    goal: resolved.goal,
    conversationId,
    idempotencyKey,
    procedureId: task.procedureId,
    stepKey: resolved.stepKey,
  })
  const validated = validateRunTrigger(trigger)
  if (!validated.ok) throw new Error(`invalid Task RunTrigger: ${validated.reason}`)

  const loop = await runButlerLoop({
    wiring: args.wiring,
    conversationId,
    content: resolved.goal,
    fromUserId: task.subject,
    projectId: "task",
    idempotencyKey,
    runTrigger: trigger,
    goal: resolved.goal,
    env,
  })

  let nextTask = task
  if (args.advance !== false && procedure && loop.finalDecision !== "AskApproval") {
    nextTask = advanceTaskAfterStep(task, procedure, Date.now())
    await tasks.update(nextTask)
  }

  return { task: nextTask, loop, goal: resolved.goal, stepKey: resolved.stepKey }
}
