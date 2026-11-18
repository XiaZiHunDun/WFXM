/**
 * P4.2: task-layer memory port.
 *
 * The task runtime reports finished turns as structured outcomes; it never
 * talks to a memory store directly. `agent-rag` provides the adapter at the
 * composition root, so this package stays free of cross-repo imports.
 *
 * Raw transcripts stay in the pi session store; only derived task summaries
 * cross this port.
 */

export type TaskMemoryStatus = "completed" | "failed" | "partial"

export interface TaskMemoryTestResult {
  readonly command: string
  readonly passed: boolean
  readonly summary?: string
}

export interface TaskMemoryEvent {
  readonly taskId: string
  readonly projectId: string
  /** What the owner asked for; used as the memory title. */
  readonly goal: string
  /** Derived summary, not a transcript dump. */
  readonly summary: string
  readonly status: TaskMemoryStatus
  readonly changedFiles?: readonly string[]
  readonly tests?: TaskMemoryTestResult
  readonly occurredAt: string
}

export interface TaskMemoryPort {
  recordTaskOutcome(event: TaskMemoryEvent): Promise<void>
}
