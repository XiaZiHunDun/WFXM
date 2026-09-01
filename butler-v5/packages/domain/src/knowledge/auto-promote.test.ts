import { describe, expect, it } from "vitest"
import { autoPromoteOldCandidates, type CandidateForPromote } from "./auto-promote.js"

const baseMs = Date.parse("2026-09-01T00:00:00Z")

const makeCandidate = (offsetMs: number): CandidateForPromote => ({
  id: `id-${offsetMs}`,
  subject: "owner",
  content: `content-${offsetMs}`,
  createdAt: new Date(baseMs + offsetMs),
})

describe("autoPromoteOldCandidates", () => {
  it("returns empty when no candidates", () => {
    const result = autoPromoteOldCandidates({
      candidates: [],
      now: new Date(baseMs + 10000),
      windowMs: 3000,
    })
    expect(result.toPromote).toHaveLength(0)
  })

  it("returns all candidates when all within window", () => {
    const candidates = [makeCandidate(0), makeCandidate(1000), makeCandidate(2000)]
    const result = autoPromoteOldCandidates({
      candidates,
      now: new Date(baseMs + 10000),
      windowMs: 3000,
    })
    // cutoff = baseMs+10000-3000 = baseMs+7000; all createdAt < baseMs+7000
    expect(result.toPromote).toHaveLength(3)
  })

  it("returns only candidates older than window", () => {
    const candidates = [makeCandidate(0), makeCandidate(5000), makeCandidate(8000)]
    const result = autoPromoteOldCandidates({
      candidates,
      now: new Date(baseMs + 10000),
      windowMs: 3000,
    })
    // cutoff = baseMs+7000; seed-0 (baseMs) and seed-5000 are older
    expect(result.toPromote).toHaveLength(2)
    expect(result.toPromote.map((c) => c.id)).toEqual(["id-0", "id-5000"])
  })

  it("handles boundary age = window (exclusive)", () => {
    const candidates = [makeCandidate(7000)]  // age = 3000ms = windowMs
    const result = autoPromoteOldCandidates({
      candidates,
      now: new Date(baseMs + 10000),
      windowMs: 3000,
    })
    // createdAt < cutoff (strict less than) — boundary NOT included
    expect(result.toPromote).toHaveLength(0)
  })

  it("handles multiple subjects", () => {
    const candidates: CandidateForPromote[] = [
      { id: "a", subject: "owner-1", content: "x", createdAt: new Date(baseMs + 0) },
      { id: "b", subject: "owner-2", content: "y", createdAt: new Date(baseMs + 0) },
      { id: "c", subject: "owner-1", content: "z", createdAt: new Date(baseMs + 5000) },
    ]
    const result = autoPromoteOldCandidates({
      candidates,
      now: new Date(baseMs + 10000),
      windowMs: 3000,
    })
    // cutoff = baseMs+7000; all 3 have age > 3000ms, all 3 across 2 subjects
    expect(result.toPromote).toHaveLength(3)
    const subjects = new Set(result.toPromote.map((c) => c.subject))
    expect(subjects.size).toBe(2)
  })
})
