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
