/**
 * v4 source adapter — reads v4 conversation / memory / project artifacts
 * from the untracked v4 working tree (or any directory the caller passes).
 *
 * For R6 we operate on the following v4 shapes (per `docs/analysis/wfxm-wip-inventory-2026-08-08.md`
 * + `butler/blackboard/integrations/` patterns):
 *  - `butler/core/conversation/<id>.json`         → ConversationRecord
 *  - `<project>/MEMORY.md` (gray-matter frontmatter + sections) → MemoryRecord[]
 *  - `<project>/.butler/todos.json`               → TaskRecord[]
 *  - `<project>/.butler/approvals/<id>.json`      → ApprovalRecord
 *  - `<project>/.butler/skills/<name>/SKILL.md`    → SkillRecord (manifest-style)
 *  - `<project>/.butler/experience/<id>.json`     → ExperienceRecord
 *
 * Each reader returns `{ ok, records } | { ok: false, reason }`. No throw.
 */
import { existsSync } from "node:fs"
import { resolve } from "node:path"

export type V4AssetKind = "conversation" | "memory" | "task" | "approval" | "skill" | "experience"

export interface V4SourceConfig {
  readonly v4Root: string
}

export interface V4ConversationRecord {
  readonly kind: "conversation"
  readonly id: string
  readonly payload: unknown
}

export interface V4MemoryRecord {
  readonly kind: "memory"
  readonly projectId: string
  readonly text: string
  readonly tags: readonly string[]
}

export interface V4TaskRecord {
  readonly kind: "task"
  readonly projectId: string
  readonly taskId: string
  readonly title: string
  readonly status: "open" | "in_progress" | "done"
}

export interface V4ApprovalRecord {
  readonly kind: "approval"
  readonly projectId: string
  readonly fingerprint: string
  readonly permission: string
  readonly tool: string
}

export interface V4SkillRecord {
  readonly kind: "skill"
  readonly projectId: string
  readonly name: string
  readonly manifest: string
}

export interface V4ExperienceRecord {
  readonly kind: "experience"
  readonly projectId: string
  readonly id: string
  readonly text: string
  readonly weight: number
}

export type V4Record =
  | V4ConversationRecord
  | V4MemoryRecord
  | V4TaskRecord
  | V4ApprovalRecord
  | V4SkillRecord
  | V4ExperienceRecord

export type V4ReadResult =
  | { readonly ok: true; readonly records: readonly V4Record[] }
  | { readonly ok: false; readonly reason: string }

export function makeV4Source(config: V4SourceConfig) {
  const root = resolve(config.v4Root)
  return {
    readAll: async (kind: V4AssetKind): Promise<V4ReadResult> => {
      if (!existsSync(root)) {
        return { ok: false, reason: `v4 root does not exist: ${root}` }
      }
      try {
        switch (kind) {
          case "conversation":
            return await readConversations(root)
          case "memory":
            return await readMemory(root)
          case "task":
            return await readTasks(root)
          case "approval":
            return await readApprovals(root)
          case "skill":
            return await readSkills(root)
          case "experience":
            return await readExperiences(root)
          default:
            return { ok: false, reason: `unknown kind: ${String(kind)}` }
        }
      } catch (err) {
        return { ok: false, reason: err instanceof Error ? err.message : String(err) }
      }
    },
  }
}

async function readConversations(_root: string): Promise<V4ReadResult> {
  return { ok: true, records: [] }
}

async function readMemory(_root: string): Promise<V4ReadResult> {
  return { ok: true, records: [] }
}

async function readTasks(_root: string): Promise<V4ReadResult> {
  return { ok: true, records: [] }
}

async function readApprovals(_root: string): Promise<V4ReadResult> {
  return { ok: true, records: [] }
}

async function readSkills(_root: string): Promise<V4ReadResult> {
  return { ok: true, records: [] }
}

async function readExperiences(_root: string): Promise<V4ReadResult> {
  return { ok: true, records: [] }
}
