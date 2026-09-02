import { findSimilarMemories } from "@butler/domain/knowledge/dedup.js"
import type { DurableMemoryStatus } from "@butler/domain/knowledge/durable-memory.js"
import type { DurableMemoryStore } from "@butler/persistence"
import { parseDedupConfig } from "../dedup-config.js"

/**
 * G2 dedup guard shared by the owner memories and document promote-memory
 * routes (split from owner-routes.ts — behavior unchanged).
 * Config is read once from env at call site (route init), matching the
 * original module-scoped `parseDedupConfig(process.env)` semantics.
 */
export function makeDedupChecker(): (opts: {
  readonly store: DurableMemoryStore
  readonly subject: string
  readonly content: string
  readonly force: boolean | undefined
}) => Promise<
  | {
      readonly existingMemoryId: string
      readonly similarity: number
      readonly status: DurableMemoryStatus
    }
  | null
> {
  // G2 dedup — module-scoped env-driven config (D41 T3 dedup-config).
  const dedupCfg = parseDedupConfig(process.env)

  return async function checkDedup(opts: {
    readonly store: DurableMemoryStore
    readonly subject: string
    readonly content: string
    readonly force: boolean | undefined
  }): Promise<
    | {
        readonly existingMemoryId: string
        readonly similarity: number
        readonly status: DurableMemoryStatus
      }
    | null
  > {
    if (!dedupCfg.enabled) return null
    if (opts.force === true) {
      // eslint-disable-next-line no-console -- operator log when no logger injected
      console.error(`[memory-dedup] forced duplicate by owner subject=${opts.subject}`)
      return null
    }
    try {
      const result = await findSimilarMemories({
        store: opts.store,
        subject: opts.subject,
        content: opts.content,
        threshold: dedupCfg.threshold,
        statuses: ["candidate", "confirmed", "rejected"],
        recentMs: dedupCfg.recentMs,
        limit: dedupCfg.limit,
      })
      if (result.best === null) return null
      return {
        existingMemoryId: result.best.id,
        similarity: result.best.similarity,
        status: result.best.status,
      }
    } catch (err) {
      // Fail-open: dedup DB error must not block owner writes (§20 #11
      // 守住 owner 自主权). Surface via stderr so operators can diagnose.
      // eslint-disable-next-line no-console -- operator log when no logger injected
      console.error(
        "[memory-dedup] check failed:",
        err instanceof Error ? err.message : String(err),
      )
      return null
    }
  }
}
