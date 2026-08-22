import { describe, expect, it } from "vitest"
import { preflightP2dSlirpEgress } from "./p2d-preflight.js"

describe("P2d slirp preflight", () => {
  it("returns structured checks for host tooling", () => {
    const result = preflightP2dSlirpEgress()
    expect(result.checks.length).toBeGreaterThanOrEqual(4)
    expect(result.checks.map((c) => c.name)).toContain("slirp4netns")
    expect(typeof result.readyForSpike).toBe("boolean")
    expect(result.note.length).toBeGreaterThan(0)
  })
})
