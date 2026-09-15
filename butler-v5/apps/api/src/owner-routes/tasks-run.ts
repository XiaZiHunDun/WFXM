/**
 * D65 T2b — Extract `tasks/:taskId/run` handler from traces-procedures-tasks.ts.
 *
 * Single-step task runner exposed to owner. Wraps `runTaskGoal` and writes
 * a `task.advance` audit row for the most-frequent task lifecycle event.
 *
 * Behavior unchanged from original inline handler. D63 T3 audit emit pattern
 * preserved: nested try/catch around `appendAuditEvent` mirrors D62 T1 F-12
 * (memories.ts) so failed audit writes log to stderr instead of vanishing.
 */
import type { Context } from "hono"
import type { Wiring } from "../wiring.js"
import { ownerAuthorized } from "../owner-auth.js"
import { runTaskGoal } from "../task-run.js"

export async function handleTaskRun(c: Context, wiring: Wiring): Promise<Response> {
  if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
  // Route param is guaranteed by the registered route path
  // `/v1/owner/tasks/:taskId/run`. `?? ""` mirrors memories-rollback.ts
  // pattern (T2a) because the extracted Context type loses Hono's route
  // narrowing that the inline closure had.
  const taskId = c.req.param("taskId") ?? ""
  const body = (await c.req.json().catch(() => ({}))) as { readonly advance?: boolean }
  try {
    const result = await runTaskGoal({
      wiring,
      taskId,
      ...(body.advance === false ? { advance: false } : {}),
    })
    // D63 T3 (audit #9 F-02): §13 audit completeness — write a
    // `task.advance` audit row for the /run path. Previously task.created
    // (line 144) and task.done (line 195) were audited (D59 T1), but the
    // /run path mutated task state via `tasks.update` without an audit
    // row. Owner queries for the most frequent task lifecycle event
    // returned zero rows.
    try {
      await wiring.runtimeStore.appendAuditEvent({
        auditId: crypto.randomUUID(),
        runId: null,
        conversationId: result.task?.conversationId ?? null,
        // D66 T1b-apps-api: thread request-scoped correlation. Owner
        // /tasks/:taskId/run is a direct API call (no inbound run); use
        // the task's conversationId when present so audit queries can
        // group advance events by conversation.
        correlationId: result.task?.conversationId ?? null,
        action: "task.advance",
        subject: result.task?.subject ?? "owner",
        detail: {
          taskId,
          stepKey: result.stepKey,
          finalDecision: result.loop.finalDecision,
        },
        createdAt: new Date(),
      })
    } catch (err) {
      // eslint-disable-next-line no-console -- operator log when no logger injected
      console.error("[traces-procedures-tasks] appendAuditEvent (task.advance) failed:", err)
    }
    return c.json({
      ok: true,
      task: result.task,
      goal: result.goal,
      stepKey: result.stepKey,
      reply: result.loop.reply,
      finalDecision: result.loop.finalDecision,
    })
  } catch (err) {
    return c.json(
      { ok: false, reason: err instanceof Error ? err.message : String(err) },
      400,
    )
  }
}
