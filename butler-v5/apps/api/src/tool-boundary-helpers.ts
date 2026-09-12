/**
 * D58 T2 (audit #2 F-01 + F-02): break the tool-boundary ↔ approval-resume
 * and tool-boundary ↔ dev-session-grant import cycles.
 *
 * Both helpers were previously owned by files that themselves imported
 * from tool-boundary, forming A↔B cycles that knip flagged and that
 * risk TDZ surprises on transitive import. They are pure (or near-pure)
 * and have no dependency on tool-boundary, so they live in their own
 * leaf module.
 */
import type { ScopedGrantRecord } from "@butler/domain/governance/types.js"
import type { RuntimeStore } from "@butler/domain/runtime.js"

/**
 * Resolve the owner subject from env. Used by both tool-boundary and
 * dev-session-grant; previously caused the tool-boundary ↔ dev-session-grant
 * cycle.
 */
export function resolveOwnerSubject(env: NodeJS.ProcessEnv, fallback: string): string {
  const raw = env["BUTLER_OWNER_WECHAT_ID"]?.trim()
  if (!raw) return fallback
  const first = raw
    .split(/[,\s]+/)
    .map((part) => part.trim())
    .find((part) => part.length > 0)
  return first ?? fallback
}

/**
 * Decrement a scoped grant's remainingUses. Previously owned by
 * approval-resume, which imported tool-boundary — moving it here breaks
 * that cycle in both directions.
 */
export async function markGrantConsumed(
  store: RuntimeStore,
  grant: ScopedGrantRecord,
): Promise<void> {
  if (grant.remainingUses === null) return
  await store.updateScopedGrantRemainingUses(grant.id, Math.max(0, grant.remainingUses - 1))
}
