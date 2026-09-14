import { describe, test, expect, vi } from "vitest"
import { computeFatigueSignal, DEFAULT_WINDOW_SECONDS, DEFAULT_COUNT_THRESHOLD } from "./signal"
import type { AuditLogReader } from "./signal"

function makeReader(events: Array<{ event_id: string; tool_name: string; ts: number; decision: 'allow' | 'deny' }>): AuditLogReader {
  return {
    readRecent: vi.fn(async (windowMs: number) => {
      const cutoff = Date.now() - windowMs
      return events.filter(e => e.ts >= cutoff)
    }),
  }
}

describe("computeFatigueSignal", () => {
  test("F1: empty audit log returns count=0", async () => {
    const reader = makeReader([])
    const signal = await computeFatigueSignal(reader)
    expect(signal.count).toBe(0)
    expect(signal.last_n_actions).toEqual([])
    expect(signal.window_seconds).toBe(DEFAULT_WINDOW_SECONDS)
  })

  test("F2: 3 actions in window returns count=3", async () => {
    const now = Date.now()
    const reader = makeReader([
      { event_id: "e1", tool_name: "read_file", ts: now - 30_000, decision: "allow" },
      { event_id: "e2", tool_name: "read_file", ts: now - 20_000, decision: "allow" },
      { event_id: "e3", tool_name: "read_file", ts: now - 10_000, decision: "allow" },
    ])
    const signal = await computeFatigueSignal(reader)
    expect(signal.count).toBe(3)
    expect(signal.last_n_actions).toHaveLength(3)
  })

  test("F3: window boundary excludes events older than window", async () => {
    const now = Date.now()
    const reader = makeReader([
      { event_id: "e1", tool_name: "read_file", ts: now - 90_000, decision: "allow" },
      { event_id: "e2", tool_name: "read_file", ts: now - 30_000, decision: "allow" },
      { event_id: "e3", tool_name: "read_file", ts: now - 80_000, decision: "allow" },
    ])
    const signal = await computeFatigueSignal(reader)
    expect(signal.count).toBe(1)
    expect(signal.last_n_actions[0].event_id).toBe("e2")
  })

  test("F4: audit log failure returns degraded signal", async () => {
    const reader: AuditLogReader = {
      readRecent: vi.fn(async () => { throw new Error("DB down") }),
    }
    const signal = await computeFatigueSignal(reader)
    expect(signal.degraded).toBe(true)
    expect(signal.count).toBe(0)
  })

  test("F5: truncated last_n_actions caps at 100", async () => {
    const now = Date.now()
    const events = Array.from({ length: 150 }, (_, i) => ({
      event_id: `e${i}`,
      tool_name: "read_file",
      ts: now - (150 - i) * 100,
      decision: "allow" as const,
    }))
    const reader = makeReader(events)
    const signal = await computeFatigueSignal(reader)
    expect(signal.count).toBe(150)
    expect(signal.last_n_actions).toHaveLength(100)
  })
})

describe("DEFAULT_*", () => {
  test("default window is 60 seconds", () => {
    expect(DEFAULT_WINDOW_SECONDS).toBe(60)
  })
  test("default threshold is 3", () => {
    expect(DEFAULT_COUNT_THRESHOLD).toBe(3)
  })
})