/**
 * Opt-in Durable Memory injection into the model working set.
 * Compaction / rolling summaries never write here.
 */
import {
  formatDurableMemoryPrefix,
  selectDurableMemoriesForWorkingSet,
} from "@butler/domain/knowledge/durable-memory.js"
import type { DurableMemoryStore } from "@butler/persistence"

function envTruthy(raw: string | undefined): boolean {
  if (!raw) return false
  const text = raw.trim().toLowerCase()
  return text === "1" || text === "true" || text === "yes" || text === "on"
}

export function isDurableMemoryInjectEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return envTruthy(env["BUTLER_V5_DURABLE_MEMORY"])
}

export async function loadDurableMemorySystemPrefix(args: {
  readonly store: DurableMemoryStore | null | undefined
  readonly subject: string
  readonly query?: string
  readonly env?: NodeJS.ProcessEnv
  readonly nowMs?: number
  readonly limit?: number
}): Promise<string | null> {
  if (!isDurableMemoryInjectEnabled(args.env ?? process.env)) return null
  if (!args.store) return null
  const subject = args.subject.trim()
  if (!subject) return null
  const records = await args.store.listBySubject({
    subject,
    status: "confirmed",
    limit: 40,
  })
  const selected = selectDurableMemoriesForWorkingSet({
    records,
    nowMs: args.nowMs ?? Date.now(),
    query: args.query,
    limit: args.limit ?? 8,
  })
  return formatDurableMemoryPrefix(selected)
}
