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

/** Result of forwarding an owner decision; only `approve()` returns it. */
export type ButlerTaskApprovalOutcome = "approved" | "denied" | "expired" | "duplicate"

export interface ButlerTaskRef {
  readonly taskId: string
  readonly projectId: string
  /** Conversation that created the task; approvals are scoped to it. */
  readonly conversationId?: string
  readonly status: ButlerTaskStatus
  readonly summary?: string
  readonly pending?: ButlerTaskPending
  /** Latest task reply, surfaced to the owner by status/list. */
  readonly lastReply?: string
  /** Failure reason of the latest turn, when status is failed. */
  readonly error?: string
  /**
   * Set by `approve()` so the butler can distinguish a real approval from an
   * expired or already-processed decision instead of claiming it ran.
   */
  readonly approvalOutcome?: ButlerTaskApprovalOutcome
}

export interface ButlerTaskPort {
  start(input: {
    readonly projectId: string
    readonly goal: string
    readonly conversationId?: string
  }): Promise<ButlerTaskRef>
  status(taskId: string): Promise<ButlerTaskRef | null>
  list(projectId?: string): Promise<readonly ButlerTaskRef[]>
  /** Forward an owner approval decision for a paused task. */
  approve?(taskId: string, approved: boolean): Promise<ButlerTaskRef | null>
  /**
   * Re-runs a stopped task (failed / idle / paused without a pending step).
   * Returns null when the task is unknown or cannot be retried.
   */
  retry?(taskId: string): Promise<ButlerTaskRef | null>
}
