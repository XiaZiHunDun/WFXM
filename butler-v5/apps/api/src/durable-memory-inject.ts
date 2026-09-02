/**
 * Opt-in Durable Memory injection into the model working set.
 * Compaction / rolling summaries never write here.
 */
import {
  formatDurableMemoryPrefix,
  selectDurableMemoriesForWorkingSet,
} from "@butler/domain/knowledge/durable-memory.js"
import { envTruthy } from "./env-util.js"
import type { DurableMemoryStore } from "@butler/persistence"


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
    ...(args.query === undefined ? {} : { query: args.query }),
    limit: args.limit ?? 8,
  })
  return formatDurableMemoryPrefix(selected)
}
