import type { V4Record } from "./v4-source.js"
import { makeV4Source } from "./v4-source.js"

export interface ShadowRunConfig {
  readonly v4Root: string
}

export interface ShadowDecision {
  readonly streamId: string
  readonly v4Decision: unknown
  readonly v5Decision: unknown
  readonly matches: boolean
}

export interface ShadowRunResult {
  readonly ok: true
  readonly decisions: readonly ShadowDecision[]
  readonly mismatches: number
}

export interface ShadowRunFailure {
  readonly ok: false
  readonly reason: string
}

export type ShadowRunOutput = ShadowRunResult | ShadowRunFailure

/**
 * Shadow runner: reads v4 inputs (via makeV4Source), produces a deterministic
 * v5 decision per input (placeholder: pass-through), then compares v4 vs v5.
 * No throw — returns a tagged result so failures are observable.
 */
export async function runShadow(config: ShadowRunConfig): Promise<ShadowRunOutput> {
  try {
    const source = makeV4Source({ v4Root: config.v4Root })
    const conversations = await source.readAll("conversation")
    if (!conversations.ok) return { ok: false, reason: conversations.reason }
    const tasks = await source.readAll("task")
    if (!tasks.ok) return { ok: false, reason: tasks.reason }

    const decisions: ShadowDecision[] = []
    let mismatches = 0
    for (const v4 of conversations.records) {
      const v5 = v4
      const matches = JSON.stringify(v4) === JSON.stringify(v5)
      if (!matches) mismatches++
      decisions.push({ streamId: deriveStreamId(v4), v4Decision: v4, v5Decision: v5, matches })
    }
    for (const v4 of tasks.records) {
      const v5 = v4
      const matches = JSON.stringify(v4) === JSON.stringify(v5)
      if (!matches) mismatches++
      decisions.push({ streamId: deriveStreamId(v4), v4Decision: v4, v5Decision: v5, matches })
    }
    return { ok: true, decisions, mismatches }
  } catch (err) {
    return { ok: false, reason: err instanceof Error ? err.message : String(err) }
  }
}

function deriveStreamId(record: V4Record): string {
  switch (record.kind) {
    case "conversation":
      return `c-${record.id}`
    case "task":
      return `t-${record.taskId}`
    case "skill":
      return `s-${record.projectId}-${record.name}`
    case "approval":
      return `a-${record.projectId}-${record.fingerprint}`
    case "experience":
      return `e-${record.projectId}-${record.id}`
    case "memory":
      return `m-${record.projectId}-${record.text.slice(0, 16)}`
  }
}
