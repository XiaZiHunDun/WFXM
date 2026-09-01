/**
 * G4: candidate auto-promote (§12).
 * Pure function — caller owns store + window.
 * Violates §12 line 599 "默认不建设" + §12 line 589 "模型生成默认 candidate 不是事实".
 * Safety net: 3d promote window + 7d post-promote rollback window + audit log + rollback API.
 */

export interface CandidateForPromote {
  readonly id: string
  readonly subject: string
  readonly content: string
  readonly createdAt: Date
}

export interface AutoPromoteOldCandidatesInput {
  readonly candidates: readonly CandidateForPromote[]
  readonly now: Date
  readonly windowMs: number
}

export interface AutoPromoteOldCandidatesResult {
  readonly toPromote: readonly CandidateForPromote[]
}

export function autoPromoteOldCandidates(
  input: AutoPromoteOldCandidatesInput,
): AutoPromoteOldCandidatesResult {
  const cutoffMs = input.now.getTime() - input.windowMs
  const toPromote = input.candidates.filter(
    (c) => c.createdAt.getTime() < cutoffMs,
  )
  return { toPromote }
}

/**
 * G4: rollback auto-promoted candidate validation.
 * Pure function — caller owns DB write.
 * Validates: status='confirmed' AND promotedBy='sweeper' AND within rollback window.
 */

export interface RollbackAutoPromotedCandidateMemory {
  readonly id: string
  readonly status: 'confirmed'
  readonly promotedBy: 'sweeper'
  readonly promotedAt: Date
}

export interface RollbackAutoPromotedCandidateInput {
  readonly memory: RollbackAutoPromotedCandidateMemory
  readonly ownerId: string
  readonly reason: string | undefined
  readonly now: Date
  /** Post-promote owner rollback window. env-derived (T6): BUTLER_V5_AUTO_PROMOTE_ROLLBACK_WINDOW_DAYS. */
  readonly rollbackWindowMs: number
}

export interface UpdatedMemory {
  readonly id: string
  readonly status: 'candidate'
  readonly updatedAt: Date
  readonly rolledBackBy: string
  readonly rolledBackAt: Date
  readonly rollbackReason: string | undefined
}

export type RollbackAutoPromotedCandidateResult =
  | { readonly ok: true; readonly updated: UpdatedMemory }
  | {
      readonly ok: false
      readonly reason:
        | 'not-confirmed'
        | 'not-auto-promoted'
        | 'rollback-window-expired'
    }

export function rollbackAutoPromotedCandidate(
  input: RollbackAutoPromotedCandidateInput,
): RollbackAutoPromotedCandidateResult {
  if (input.memory.status !== 'confirmed') {
    return { ok: false, reason: 'not-confirmed' }
  }
  if (input.memory.promotedBy !== 'sweeper') {
    return { ok: false, reason: 'not-auto-promoted' }
  }
  const rollbackDeadlineMs =
    input.memory.promotedAt.getTime() + input.rollbackWindowMs
  if (input.now.getTime() > rollbackDeadlineMs) {
    return { ok: false, reason: 'rollback-window-expired' }
  }
  return {
    ok: true,
    updated: {
      id: input.memory.id,
      status: 'candidate',
      updatedAt: input.now,
      rolledBackBy: input.ownerId,
      rolledBackAt: input.now,
      rollbackReason: input.reason,
    },
  }
}
