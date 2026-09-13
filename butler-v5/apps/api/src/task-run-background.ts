import { runTaskGoal } from "./task-run.js"
import { envTruthy } from "./env-util.js"
import type { Wiring } from "./wiring.js"
import { safeOwnerError } from "./safe-owner-error.js"
import {
  formatTaskRunCompletionNotify,
  isRunNotifyEnabled,
  sendWechatProactiveNotify,
} from "./wechat-run-notify.js"


/** Background /运行 when 1 or when run notify is enabled. */
export function isTaskRunAsyncEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return envTruthy(env["BUTLER_V5_TASK_RUN_ASYNC"]) || isRunNotifyEnabled(env)
}

const inFlight = new Set<string>()

export function scheduleBackgroundTaskRun(args: {
  readonly wiring: Wiring
  readonly taskId: string
  readonly subject: string
  readonly title: string
  readonly env?: NodeJS.ProcessEnv
}): { readonly ok: true } | { readonly ok: false; readonly reason: string } {
  if (inFlight.has(args.taskId)) {
    return { ok: false, reason: "该待办已在后台运行中" }
  }
  inFlight.add(args.taskId)
  const env = args.env ?? process.env
  void (async () => {
    try {
      const result = await runTaskGoal({
        wiring: args.wiring,
        taskId: args.taskId,
        env,
      })
      if (isRunNotifyEnabled(env)) {
        await sendWechatProactiveNotify({
          to: args.subject,
          text: formatTaskRunCompletionNotify({
            taskId: args.taskId,
            title: args.title,
            decision: result.loop.finalDecision,
            reply: result.loop.reply,
            ok: true,
          }),
          env,
        })
      }
    } catch (err) {
      if (isRunNotifyEnabled(env)) {
        await sendWechatProactiveNotify({
          to: args.subject,
          text: formatTaskRunCompletionNotify({
            taskId: args.taskId,
            title: args.title,
            decision: "Error",
            // D62 T1 (audit #3 F-11): replace raw err.message with safe
            // fallback in the notify path. Full error logged to stderr
            // via safeOwnerError. Owner sees Chinese reason + taskId,
            // not DB/network internals.
            reply: safeOwnerError(err, "运行失败，请稍后重试", {
              operation: "background-task-run",
              taskId: args.taskId,
            }),
            ok: false,
          }),
          env,
        })
      }
    } finally {
      inFlight.delete(args.taskId)
    }
  })()
  return { ok: true }
}
