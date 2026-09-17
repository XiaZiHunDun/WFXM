import { describe, test, expect, vi } from "vitest"
import { listFatigueSequences, replayFatigueSequence } from "./replay"
import type { AuditLogReader, AuditEventSummary } from "./signal"

const now = Date.now()
function makeReader(
  events: {
    event_id: string
    tool_name: string
    actor: string
    ts: number
    decision: 'allow'
  }[],
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
    const [first, second] = result.sequences
    expect(first?.start_ts).toBeGreaterThan(second?.start_ts as number)
  })
})

describe("replayFatigueSequence", () => {
  test("R3: mixed write + send_email → undo ok + irreversible", async () => {
    const reader = makeReader([
      { event_id: "e-write", tool_name: "write_file", actor: "owner", ts: now, decision: "allow" },
      { event_id: "e-send", tool_name: "send_email", actor: "owner", ts: now, decision: "allow" },
    ])
    // D70 T1: undo dispatcher is now required; provide a stub that
    // succeeds for every reversible event so we can verify the
    // irreversible vs replayed routing.
    const undo = async () => ({ ok: true as const })
    const result = await replayFatigueSequence(reader, ["e-write", "e-send"], "owner", undo)
    expect(result.replayed).toContain("e-write")
    expect(result.irreversible).toContain("e-send")
    expect(result.failed).toEqual([])
  })

  test("R3b: undo dispatcher failure → event lands in failed, not replayed", async () => {
    const reader = makeReader([
      { event_id: "e-write", tool_name: "write_file", actor: "owner", ts: now, decision: "allow" },
    ])
    const undo = async () => ({ ok: false as const, reason: "no undo implementation for write_file at this site" })
    const result = await replayFatigueSequence(reader, ["e-write"], "owner", undo)
    expect(result.replayed).toEqual([])
    expect(result.irreversible).toEqual([])
    expect(result.failed).toEqual([{ event_id: "e-write", reason: "no undo implementation for write_file at this site" }])
  })

  test("R3c: undo dispatcher NOT called for irreversible tools", async () => {
    const reader = makeReader([
      { event_id: "e-send", tool_name: "send_email", actor: "owner", ts: now, decision: "allow" },
    ])
    let undoCalls = 0
    const undo = async () => {
      undoCalls += 1
      return { ok: true as const }
    }
    const result = await replayFatigueSequence(reader, ["e-send"], "owner", undo)
    expect(result.irreversible).toContain("e-send")
    expect(result.replayed).toEqual([])
    expect(undoCalls).toBe(0) // irreversible short-circuits before undo dispatch
  })

  test("R4: cross-actor event_ids rejected (security)", async () => {
    const reader = makeReader([
      { event_id: "e1", tool_name: "write_file", actor: "owner-A", ts: now, decision: "allow" },
    ])
    const undo = async () => ({ ok: true as const })
    await expect(
      replayFatigueSequence(reader, ["e1"], "owner-B", undo)
    ).rejects.toThrow(/cross-actor|not owner/i)
  })
})