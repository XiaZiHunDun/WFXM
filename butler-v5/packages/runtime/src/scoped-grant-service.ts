import type { ScopedGrantRecord } from "@butler/domain/governance/types.js"
import type { RuntimeStore } from "@butler/domain/runtime.js"
import { sandboxProfileForApprovedCapability } from "./sandbox/profiles.js"

export interface IssuePreconfiguredGrantsInput {
  readonly store: RuntimeStore
  readonly runId: string
  readonly subject: string
  readonly capabilities: readonly string[]
  readonly maxUses: number
  readonly ttlMs: number
  readonly approvalId?: string | null
  readonly createdAt?: Date
  /** When true, zero remainingUses on active grants before issuing fresh ones. */
  readonly refreshExisting?: boolean
}

/**
 * Issue multi-use ScopedGrants for Owner-preconfigured sessions (dev session,
 * delegation child run). All production grant issuance should funnel here or
 * through approval-runtime.approveWaitingStep.
 */
export async function issuePreconfiguredGrants(
  input: IssuePreconfiguredGrantsInput,
): Promise<readonly ScopedGrantRecord[]> {
  const now = input.createdAt ?? new Date()
  const expiresAt = new Date(now.getTime() + input.ttlMs)
  const issued: ScopedGrantRecord[] = []

  for (const capability of input.capabilities) {
    if (input.refreshExisting === true) {
      const existing = await input.store.findActiveGrant({
        runId: input.runId,
        subject: input.subject,
        capability,
        now,
      })
      if (existing && existing.remainingUses !== null && existing.remainingUses > 0) {
        await input.store.updateScopedGrantRemainingUses(existing.id, 0)
      }
    } else {
      const existing = await input.store.findActiveGrant({
        runId: input.runId,
        subject: input.subject,
        capability,
        now,
      })
      if (existing) continue
    }

    const grant = await input.store.createScopedGrant({
      grantId: crypto.randomUUID(),
      runId: input.runId,
      subject: input.subject,
      scope: {
        capabilities: [capability],
        maxUses: input.maxUses,
      },
      remainingUses: input.maxUses,
      expiresAt,
      createdAt: now,
      delegable: false,
      approvalId: input.approvalId ?? null,
      sandboxProfile: sandboxProfileForApprovedCapability(capability),
      networkAllowlist: null,
    })
    issued.push(grant)
  }

  return issued
}
