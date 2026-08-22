/**
 * Task / Procedure baseline (DESIGN § / P4).
 * Task = Owner-visible durable todo; Procedure = immutable linear template.
 * No DAG, no parallel merge, no second Run Engine.
 */

export type TaskId = string
export type ProcedureId = string

export type TaskStatus = "open" | "done" | "cancelled"

export interface ProcedureStepTemplate {
  readonly key: string
  readonly title: string
  /** Goal text used when this step fires a Run. */
  readonly goal: string
  /**
   * Optional condition label only (MVP does not evaluate expressions).
   * Present for forward-compatible conditional templates.
   */
  readonly when?: string
}

export interface ProcedureRecord {
  readonly id: ProcedureId
  readonly name: string
  readonly version: number
  readonly steps: readonly ProcedureStepTemplate[]
  readonly createdAt: number
}

export interface TaskRecord {
  readonly id: TaskId
  readonly subject: string
  readonly title: string
  readonly goal: string
  readonly status: TaskStatus
  /** Optional conversation this todo is associated with (not required). */
  readonly conversationId: string | null
  readonly procedureId: string | null
  /** 0-based index into Procedure.steps when bound; null if free-form. */
  readonly procedureStepIndex: number | null
  readonly createdAt: number
  readonly updatedAt: number
}

export interface CreateProcedureInput {
  readonly id?: string
  readonly name: string
  readonly version?: number
  readonly steps: readonly ProcedureStepTemplate[]
  readonly nowMs?: number
}

export interface CreateTaskInput {
  readonly id?: string
  readonly subject: string
  readonly title: string
  readonly goal: string
  readonly status?: TaskStatus
  readonly conversationId?: string | null
  readonly procedureId?: string | null
  readonly procedureStepIndex?: number | null
  readonly nowMs?: number
}

export type TaskValidation =
  | { readonly ok: true; readonly value: TaskRecord }
  | { readonly ok: false; readonly reason: string }

export type ProcedureValidation =
  | { readonly ok: true; readonly value: ProcedureRecord }
  | { readonly ok: false; readonly reason: string }

export function createProcedureRecord(input: CreateProcedureInput): ProcedureValidation {
  const name = input.name.trim()
  if (!name) return { ok: false, reason: "name is required" }
  if (!Array.isArray(input.steps) || input.steps.length === 0) {
    return { ok: false, reason: "steps must be a non-empty array" }
  }
  const steps: ProcedureStepTemplate[] = []
  const keys = new Set<string>()
  for (const raw of input.steps) {
    if (!raw || typeof raw !== "object") return { ok: false, reason: "invalid step" }
    const key = String(raw.key ?? "").trim()
    const title = String(raw.title ?? "").trim()
    const goal = String(raw.goal ?? "").trim()
    if (!key || !title || !goal) {
      return { ok: false, reason: "each step needs key, title, and goal" }
    }
    if (keys.has(key)) return { ok: false, reason: `duplicate step key: ${key}` }
    keys.add(key)
    const when = typeof raw.when === "string" && raw.when.trim() ? raw.when.trim() : undefined
    steps.push({ key, title, goal, ...(when ? { when } : {}) })
  }
  const version = input.version === undefined ? 1 : Math.floor(input.version)
  if (!Number.isFinite(version) || version < 1) {
    return { ok: false, reason: "version must be >= 1" }
  }
  const nowMs = input.nowMs ?? Date.now()
  return {
    ok: true,
    value: {
      id: (input.id ?? crypto.randomUUID()).trim(),
      name,
      version,
      steps,
      createdAt: nowMs,
    },
  }
}

export function createTaskRecord(input: CreateTaskInput): TaskValidation {
  const subject = input.subject.trim()
  const title = input.title.trim()
  const goal = input.goal.trim()
  if (!subject) return { ok: false, reason: "subject is required" }
  if (!title) return { ok: false, reason: "title is required" }
  if (!goal) return { ok: false, reason: "goal is required" }
  const status = input.status ?? "open"
  if (status !== "open" && status !== "done" && status !== "cancelled") {
    return { ok: false, reason: "invalid status" }
  }
  const nowMs = input.nowMs ?? Date.now()
  const procedureStepIndex =
    input.procedureStepIndex === undefined || input.procedureStepIndex === null
      ? null
      : Math.floor(input.procedureStepIndex)
  if (procedureStepIndex !== null && procedureStepIndex < 0) {
    return { ok: false, reason: "procedureStepIndex must be >= 0" }
  }
  return {
    ok: true,
    value: {
      id: (input.id ?? crypto.randomUUID()).trim(),
      subject,
      title,
      goal,
      status,
      conversationId: input.conversationId?.trim() || null,
      procedureId: input.procedureId?.trim() || null,
      procedureStepIndex,
      createdAt: nowMs,
      updatedAt: nowMs,
    },
  }
}

export function resolveTaskRunGoal(
  task: TaskRecord,
  procedure: ProcedureRecord | null,
): { readonly ok: true; readonly goal: string; readonly stepKey: string | null } | {
  readonly ok: false
  readonly reason: string
} {
  if (task.status !== "open") return { ok: false, reason: `task is ${task.status}` }
  if (!task.procedureId || !procedure) {
    return { ok: true, goal: task.goal, stepKey: null }
  }
  if (procedure.id !== task.procedureId) {
    return { ok: false, reason: "procedure mismatch" }
  }
  const idx = task.procedureStepIndex ?? 0
  const step = procedure.steps[idx]
  if (!step) return { ok: false, reason: `procedure step index ${idx} out of range` }
  return { ok: true, goal: step.goal, stepKey: step.key }
}

export function advanceTaskAfterStep(
  task: TaskRecord,
  procedure: ProcedureRecord,
  nowMs: number,
): TaskRecord {
  const idx = (task.procedureStepIndex ?? 0) + 1
  if (idx >= procedure.steps.length) {
    return { ...task, status: "done", procedureStepIndex: idx - 1, updatedAt: nowMs }
  }
  const next = procedure.steps[idx]
  return {
    ...task,
    goal: next?.goal ?? task.goal,
    procedureStepIndex: idx,
    updatedAt: nowMs,
  }
}

export function defaultTaskConversationId(taskId: string): string {
  return `task-${taskId}`
}
