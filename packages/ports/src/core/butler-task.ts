/**
 * P4.2: butler -> task-layer dispatch port.
 *
 * The butler runtime routes work to the task layer through this port; it does
 * not know whether the task layer is pi-backed, another runtime, or a stub.
 * Approval decisions are forwarded here instead of re-implementing task state.
 */

export type ButlerTaskStatus = "idle" | "running" | "paused" | "failed" | "closed"

/** What the owner must confirm before the task can continue. */
export interface ButlerTaskPending {
  readonly toolName: string
  readonly reason: string
  readonly requestedAt?: string
}

export interface ButlerTaskRef {
  readonly taskId: string
  readonly projectId: string
  readonly status: ButlerTaskStatus
  readonly summary?: string
  readonly pending?: ButlerTaskPending
  /** Latest task reply, surfaced to the owner by status/list. */
  readonly lastReply?: string
  /** Failure reason of the latest turn, when status is failed. */
  readonly error?: string
}

export interface ButlerTaskPort {
  start(input: { readonly projectId: string; readonly goal: string }): Promise<ButlerTaskRef>
  status(taskId: string): Promise<ButlerTaskRef | null>
  list(projectId?: string): Promise<readonly ButlerTaskRef[]>
  /** Forward an owner approval decision for a paused task. */
  approve?(taskId: string, approved: boolean): Promise<ButlerTaskRef | null>
}
