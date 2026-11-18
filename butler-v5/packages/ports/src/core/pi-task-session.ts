/**
 * P4.1: task-level session contract for the pi-native task layer.
 *
 * The task layer is stateless: an Agent is rebuilt from a JSON snapshot on
 * every turn. The butler layer owns durability through this port and can swap
 * the in-memory store for the Drizzle-backed table.
 */

export type PiTaskSessionStatus = "idle" | "running" | "paused" | "closed" | "failed"

/** A tool call that was blocked pending owner approval. */
export interface PiTaskPendingStep {
  readonly toolCallId: string
  readonly toolName: string
  readonly args: Readonly<Record<string, unknown>>
  readonly reason: string
  readonly requestedAt: string
}

/**
 * JSON-serializable pi transcript. `messages` stays `unknown[]` here so the
 * port package does not depend on pi types; the runtime narrows it after
 * validating the snapshot.
 */
export interface PiTaskSessionSnapshot {
  readonly version: 1
  readonly systemPrompt: string
  readonly summary?: string
  readonly messages: readonly unknown[]
}

export interface PiTaskSessionRecord {
  readonly taskId: string
  readonly projectId: string
  readonly cwd: string
  readonly status: PiTaskSessionStatus
  readonly snapshot: PiTaskSessionSnapshot
  readonly pendingStep: PiTaskPendingStep | null
  readonly createdAt: string
  readonly updatedAt: string
}

export interface PiTaskSessionStore {
  load(taskId: string): Promise<PiTaskSessionRecord | null>
  save(record: PiTaskSessionRecord): Promise<void>
  delete(taskId: string): Promise<void>
}
