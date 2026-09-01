import { describe, expect, it } from "vitest"
import {
  rollbackAutoPromotedCandidate,
  type RollbackAutoPromotedCandidateMemory,
} from "./auto-promote.js"

const baseMs = Date.parse("2026-09-01T00:00:00Z")
const SEVEN_DAYS_MS = 7 * 24 * 3_600_000

const makeMemory = (
  overrides: Partial<{
    status: 'confirmed'
    promotedBy: 'sweeper'
    promotedAt: Date
  }> = {},
): RollbackAutoPromotedCandidateMemory => ({
  id: "test-id",
  status: 'confirmed' as const,
  promotedBy: 'sweeper' as const,
  promotedAt: new Date(baseMs),
  ...overrides,
})

describe("rollbackAutoPromotedCandidate", () => {
  it("returns ok with updated memory when valid", () => {
    const result = rollbackAutoPromotedCandidate({
      memory: makeMemory({ promotedAt: new Date(baseMs) }),
      ownerId: "owner-123",
      reason: "looks wrong",
      now: new Date(baseMs + 1000),
      rollbackWindowMs: SEVEN_DAYS_MS,
    })
    expect(result.ok).toBe(true)
    if (!result.ok) throw new Error("expected ok")
    expect(result.updated.status).toBe('candidate')
    expect(result.updated.id).toBe("test-id")
    expect(result.updated.rolledBackBy).toBe("owner-123")
    expect(result.updated.rollbackReason).toBe("looks wrong")
  })

  it("returns not-confirmed when status != 'confirmed'", () => {
    // Cast to bypass literal type check (the runtime validates)
    const memory = {
      id: "x",
      status: 'candidate' as 'confirmed',
      promotedBy: 'sweeper' as const,
      promotedAt: new Date(baseMs),
    }
    const result = rollbackAutoPromotedCandidate({
      memory,
      ownerId: "owner-123",
      reason: "test",
      now: new Date(baseMs + 1000),
      rollbackWindowMs: SEVEN_DAYS_MS,
    })
    expect(result.ok).toBe(false)
    if (result.ok) throw new Error("expected not ok")
    expect(result.reason).toBe('not-confirmed')
  })

  it("returns not-auto-promoted when promotedBy != 'sweeper'", () => {
    const result = rollbackAutoPromotedCandidate({
      memory: makeMemory({ promotedBy: 'owner' as 'sweeper' }),
      ownerId: "owner-123",
      reason: "test",
      now: new Date(baseMs + 1000),
      rollbackWindowMs: SEVEN_DAYS_MS,
    })
    expect(result.ok).toBe(false)
    if (result.ok) throw new Error("expected not ok")
    expect(result.reason).toBe('not-auto-promoted')
  })

  it("returns rollback-window-expired when past deadline", () => {
    const result = rollbackAutoPromotedCandidate({
      memory: makeMemory({ promotedAt: new Date(baseMs) }),
      ownerId: "owner-123",
      reason: "test",
      now: new Date(baseMs + 8 * 24 * 3_600_000),
      rollbackWindowMs: SEVEN_DAYS_MS,
    })
    expect(result.ok).toBe(false)
    if (result.ok) throw new Error("expected not ok")
    expect(result.reason).toBe('rollback-window-expired')
  })

  it("handles no reason (undefined)", () => {
    const result = rollbackAutoPromotedCandidate({
      memory: makeMemory(),
      ownerId: "owner-123",
      reason: undefined,
      now: new Date(baseMs + 1000),
      rollbackWindowMs: SEVEN_DAYS_MS,
    })
    expect(result.ok).toBe(true)
    if (!result.ok) throw new Error("expected ok")
    expect(result.updated.rollbackReason).toBeUndefined()
  })

  it("handles with reason", () => {
    const result = rollbackAutoPromotedCandidate({
      memory: makeMemory(),
      ownerId: "owner-123",
      reason: "this is a factually wrong memory",
      now: new Date(baseMs + 1000),
      rollbackWindowMs: SEVEN_DAYS_MS,
    })
    expect(result.ok).toBe(true)
    if (!result.ok) throw new Error("expected ok")
    expect(result.updated.rollbackReason).toBe("this is a factually wrong memory")
  })
})
