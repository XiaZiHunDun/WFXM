import { canTransitionRun } from "@butler/domain/runtime.js"
import type { RuntimeStore, StoredRun } from "@butler/domain/runtime.js"

export class IllegalRunTransitionError extends Error {
  constructor(
    public readonly runId: string,
    public readonly from: string,
    public readonly to: string,
  ) {
    super(`illegal Run transition ${runId}: ${from} -> ${to}`)
  }
}

async function transitionChecked(
  store: RuntimeStore,
  run: StoredRun,
  to: StoredRun["status"],
  updatedAt: Date,
): Promise<StoredRun> {
  if (!canTransitionRun(run.status, to)) {
    throw new IllegalRunTransitionError(run.id, run.status, to)
  }
  return store.transitionRunStatus(run.id, run.version, to, updatedAt)
}

/** Owner cancel: end an active Run as cancelled. */
export async function cancelRun(
  store: RuntimeStore,
  runId: string,
  options: {
    readonly subject: string
    readonly reason?: string
    readonly now?: Date
  },
): Promise<StoredRun> {
  const run = await store.getRun(runId)
  if (!run) throw new Error(`run not found: ${runId}`)
  const now = options.now ?? new Date()
  const cancelled = await transitionChecked(store, run, "cancelled", now)
  await store.appendAuditEvent({
    auditId: crypto.randomUUID(),
    runId: cancelled.id,
    conversationId: cancelled.conversationId,
    action: "run.cancelled",
    subject: options.subject,
    detail: { reason: options.reason ?? "owner_cancel", from: run.status },
    createdAt: now,
  })
  return cancelled
}

/** D4-arch-align §20 #7: Owner cancel that propagates to all descendants.
 *
 * Cancels `runId` and recursively cancels every descendant child Run
 * (parentRunId chain). Each cascaded cancel emits a `run.cancelled`
 * audit with `reason: "parent_cascade"` + ancestor `parentRunId` so
 * the audit trail distinguishes cascade-induced cancels from owner
 * cancels.
 *
 * Returns the list of cancelled Runs in BFS order (parent first, then
 * children, then grandchildren). Already-terminal runs are skipped
 * (idempotent: cancelling a `cancelled` Run is a no-op).
 */
export async function cancelRunCascade(
  store: RuntimeStore,
  runId: string,
  options: {
    readonly subject: string
    readonly reason?: string
    readonly now?: Date
  },
): Promise<readonly StoredRun[]> {
  const now = options.now ?? new Date()
  const cancelledOrder: StoredRun[] = []
  const visited = new Set<string>()

  async function cancelRecursive(targetRunId: string): Promise<void> {
    if (visited.has(targetRunId)) return
    visited.add(targetRunId)
    const children = await store.findChildRuns(targetRunId)
    // Cancel children first so descendants terminate before ancestor reports
    // `cancelled`; audit order still records ancestor first via outer caller.
    for (const child of children) {
      await cancelRecursive(child.id)
    }
    const run = await store.getRun(targetRunId)
    if (!run) return
    if (run.status === "cancelled" || run.status === "failed" || run.status === "succeeded") {
      return
    }
    const cancelled = await transitionChecked(store, run, "cancelled", now)
    cancelledOrder.push(cancelled)
    await store.appendAuditEvent({
      auditId: crypto.randomUUID(),
      runId: cancelled.id,
      conversationId: cancelled.conversationId,
      action: "run.cancelled",
      subject: options.subject,
      detail: {
        reason: options.reason ?? "owner_cancel_cascade",
        from: run.status,
        ancestorRunId: runId === cancelled.id ? null : runId,
      },
      createdAt: now,
    })
  }

  // Cancel the root run last so audit lineage reads parent → child.
  const rootChildren = await store.findChildRuns(runId)
  for (const child of rootChildren) {
    await cancelRecursive(child.id)
  }
  await cancelRecursive(runId)
  return cancelledOrder
}

/** Expire a single Run when past deadline (or forced). */
export async function expireRun(
  store: RuntimeStore,
  runId: string,
  options: {
    readonly subject?: string
    readonly now?: Date
    readonly force?: boolean
  } = {},
): Promise<StoredRun> {
  const run = await store.getRun(runId)
  if (!run) throw new Error(`run not found: ${runId}`)
  const now = options.now ?? new Date()
  if (!options.force) {
    if (!run.deadline) throw new Error(`run ${runId} has no deadline`)
    if (run.deadline.getTime() > now.getTime()) {
      throw new Error(`run ${runId} deadline not reached`)
    }
  }
  const expired = await transitionChecked(store, run, "expired", now)
  await store.appendAuditEvent({
    auditId: crypto.randomUUID(),
    runId: expired.id,
    conversationId: expired.conversationId,
    action: "run.expired",
    subject: options.subject ?? "system",
    detail: { deadline: run.deadline?.toISOString() ?? null, from: run.status },
    createdAt: now,
  })
  return expired
}

/** Sweep active Runs whose deadline is in the past. */
export async function expireOverdueRuns(
  store: RuntimeStore,
  options: { readonly now?: Date; readonly subject?: string } = {},
): Promise<readonly StoredRun[]> {
  const now = options.now ?? new Date()
  const overdue = await store.listRunsPastDeadline(now)
  const expired: StoredRun[] = []
  for (const run of overdue) {
    try {
      expired.push(
        await expireRun(store, run.id, {
          now,
          subject: options.subject ?? "system",
          force: true,
        }),
      )
    } catch (err) {
      if (err instanceof IllegalRunTransitionError) continue
      throw err
    }
  }
  return expired
}

export interface WaitingExternalRequest {
  readonly runId: string
  readonly conversationId: string
  readonly subject: string
  readonly reason: string
  readonly resumeHint?: string
}

/** Pause a running Run for an external dependency (minimal A4 surface). */
export async function enterWaitingExternal(
  store: RuntimeStore,
  request: WaitingExternalRequest,
): Promise<{ readonly stepId: string; readonly run: StoredRun }> {
  const run = await store.getRun(request.runId)
  if (!run) throw new Error(`run not found: ${request.runId}`)
  const now = new Date()
  const waiting = await transitionChecked(store, run, "waiting_external", now)
  const stepId = crypto.randomUUID()
  await store.createStep({
    id: stepId,
    runId: request.runId,
    kind: "external",
    status: "waiting",
    input: {
      _tag: "WaitingExternal",
      reason: request.reason,
      conversationId: request.conversationId,
      subject: request.subject,
      ...(request.resumeHint ? { resumeHint: request.resumeHint } : {}),
    },
    createdAt: now,
  })
  await store.appendAuditEvent({
    auditId: crypto.randomUUID(),
    runId: request.runId,
    conversationId: request.conversationId,
    action: "run.waiting_external",
    subject: request.subject,
    detail: { stepId, reason: request.reason },
    createdAt: now,
  })
  return { stepId, run: waiting }
}

/** Resume a waiting_external Run back to running (same Run). */
export async function resumeFromWaitingExternal(
  store: RuntimeStore,
  runId: string,
  options: { readonly subject: string; readonly stepId?: string } = {
    subject: "system",
  },
): Promise<StoredRun> {
  const run = await store.getRun(runId)
  if (!run) throw new Error(`run not found: ${runId}`)
  if (run.status !== "waiting_external") {
    throw new Error(`run ${runId} is ${run.status}, expected waiting_external`)
  }
  const now = new Date()
  if (options.stepId) {
    const step = await store.getStep(options.stepId)
    if (step && step.kind === "external" && step.status === "waiting") {
      await store.updateStep({
        stepId: options.stepId,
        status: "succeeded",
        output: { resumedBy: options.subject },
        updatedAt: now,
      })
    }
  }
  const resumed = await transitionChecked(store, run, "running", now)
  await store.appendAuditEvent({
    auditId: crypto.randomUUID(),
    runId,
    conversationId: run.conversationId,
    action: "run.resumed_external",
    subject: options.subject,
    detail: { stepId: options.stepId ?? null },
    createdAt: now,
  })
  return resumed
}
