import { describe, test, expect, vi } from "vitest"
import { listFatigueSequences, replayFatigueSequence } from "./replay"
import type { AuditLogReader, AuditEventSummary } from "./signal"

const now = Date.now()
function makeReader(
  events: Array<{
    event_id: string
    tool_name: string
    actor: string
    ts: number
    decision: 'allow'
  }>,
): AuditLogReader {
  return {
    readRecent: vi.fn(async (): Promise<readonly AuditEventSummary[]> => events),
  }
}

describe("listFatigueSequences", () => {
  test("R1: empty audit returns empty sequences", async () => {
    const reader = makeReader([])
    const result = await listFatigueSequences(reader, "owner", 60)
    expect(result.sequences).toEqual([])
    expect(result.degraded).toBeUndefined()
  })

  test("R2: 2 separate sequences sorted DESC by start_ts", async () => {
    const reader = makeReader([
      { event_id: "e1", tool_name: "read_file", actor: "owner", ts: now - 60_000, decision: "allow" },
      { event_id: "e2", tool_name: "read_file", actor: "owner", ts: now - 50_000, decision: "allow" },
      { event_id: "e3", tool_name: "read_file", actor: "owner", ts: now - 40_000, decision: "allow" },
      // gap of 10s
      { event_id: "e7", tool_name: "read_file", actor: "owner", ts: now - 20_000, decision: "allow" },
      { event_id: "e8", tool_name: "read_file", actor: "owner", ts: now - 15_000, decision: "allow" },
      { event_id: "e9", tool_name: "read_file", actor: "owner", ts: now - 10_000, decision: "allow" },
      { event_id: "e10", tool_name: "read_file", actor: "owner", ts: now - 5_000, decision: "allow" },
      { event_id: "e11", tool_name: "read_file", actor: "owner", ts: now - 1_000, decision: "allow" },
    ])
    const result = await listFatigueSequences(reader, "owner", 60)
    expect(result.sequences).toHaveLength(2)
    expect(result.sequences[0]?.count).toBe(5) // most recent
    expect(result.sequences[1]?.count).toBe(3)
    // DESC by start_ts
    expect(result.sequences[0]!.start_ts).toBeGreaterThan(result.sequences[1]!.start_ts)
  })
})

describe("replayFatigueSequence", () => {
  test("R3: mixed write + send_email → replayed + irreversible", async () => {
    const reader = makeReader([
      { event_id: "e-write", tool_name: "write_file", actor: "owner", ts: now, decision: "allow" },
      { event_id: "e-send", tool_name: "send_email", actor: "owner", ts: now, decision: "allow" },
    ])
    const result = await replayFatigueSequence(reader, ["e-write", "e-send"], "owner")
    expect(result.replayed).toContain("e-write")
    expect(result.irreversible).toContain("e-send")
  })

  test("R4: cross-actor event_ids rejected (security)", async () => {
    const reader = makeReader([
      { event_id: "e1", tool_name: "write_file", actor: "owner-A", ts: now, decision: "allow" },
    ])
    await expect(
      replayFatigueSequence(reader, ["e1"], "owner-B")
    ).rejects.toThrow(/cross-actor|not owner/i)
  })
})