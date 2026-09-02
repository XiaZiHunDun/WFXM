/**
 * Opt-in Project Knowledge injection into the model working set.
 */
import {
  formatProjectKnowledgePrefix,
  resolveProjectKnowledgeInboundProjectId,
  selectProjectKnowledgeForWorkingSet,
} from "@butler/domain/knowledge/project-knowledge.js"
import type { ProjectKnowledgeStore } from "@butler/persistence"

function envTruthy(raw: string | undefined): boolean {
  if (!raw) return false
  const text = raw.trim().toLowerCase()
  return text === "1" || text === "true" || text === "yes" || text === "on"
}

export function isProjectKnowledgeInjectEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return envTruthy(env["BUTLER_V5_PROJECT_KNOWLEDGE"])
}

export async function loadProjectKnowledgeSystemPrefix(args: {
  readonly store: ProjectKnowledgeStore | null | undefined
  readonly projectId: string
  readonly query?: string
  readonly env?: NodeJS.ProcessEnv
  readonly limit?: number
}): Promise<string | null> {
  if (!isProjectKnowledgeInjectEnabled(args.env ?? process.env)) return null
  if (!args.store) return null
  const env = args.env ?? process.env
  const projectId = resolveProjectKnowledgeInboundProjectId(args.projectId, env)
  if (!projectId) return null
  const records = await args.store.listByProject({ projectId, limit: 40 })
  const selected = selectProjectKnowledgeForWorkingSet({
    records,
    ...(args.query === undefined ? {} : { query: args.query }),
    limit: args.limit ?? 6,
  })
  return formatProjectKnowledgePrefix(selected)
}
