import { describe, test, expect, vi } from "vitest"
import { auditFatigueReader } from "./audit-reader"
import type { AuditEventRecord, RuntimeStore } from "@butler/domain/runtime.js"

function makeStore(
  rows: readonly AuditEventRecord[],
): RuntimeStore {
  return {
    listRecentAuditEvents: vi.fn(async () => rows),
  } as unknown as RuntimeStore
}

const baseEvent = (overrides: Partial<AuditEventRecord> = {}): AuditEventRecord => ({
  auditId: "audit-1",
  runId: "run-1",
  conversationId: "conv-1",
  action: "fatigue.decision",
  subject: "read_file",
  detail: {},
  createdAt: new Date("2026-09-17T10:00:00Z"),
  correlationId: null,
  ...overrides,
})

describe("auditFatigueReader", () => {
  test("R1: maps AuditEventRecord fields to AuditEventSummary", async () => {
    const created = new Date("2026-09-17T10:00:00Z")
    const store = makeStore([baseEvent({ auditId: "a1", subject: "write_file", createdAt: created })])
    const reader = auditFatigueReader(store)
    const result = await reader.readRecent(60_000)
    expect(result).toEqual([
      {
        event_id: "a1",
        tool_name: "write_file",
        actor: "owner",
        ts: created.getTime(),
        decision: "allow",
      },
    ])
  })

  test("R2: passes windowMs + limit to store.listRecentAuditEvents", async () => {
    const list = vi.fn(async () => [])
    const store = { listRecentAuditEvents: list } as unknown as RuntimeStore
    const reader = auditFatigueReader(store, { limit: 25 })
    await reader.readRecent(120_000)
    expect(list).toHaveBeenCalledWith({ windowMs: 120_000, limit: 25 })
  })

  test("R3: default limit is 100 when options omitted", async () => {
    const list = vi.fn(async () => [])
    const store = { listRecentAuditEvents: list } as unknown as RuntimeStore
    const reader = auditFatigueReader(store)
    await reader.readRecent(60_000)
    expect(list).toHaveBeenCalledWith({ windowMs: 60_000, limit: 100 })
  })

  test("R4: empty store returns empty array", async () => {
    const reader = auditFatigueReader(makeStore([]))
    const result = await reader.readRecent(60_000)
    expect(result).toEqual([])
  })

  test("R5: subject column becomes tool_name (per D58 T1 spec)", async () => {
    const store = makeStore([
      baseEvent({ auditId: "x", subject: "send_email" }),
      baseEvent({ auditId: "y", subject: "read_file" }),
      baseEvent({ auditId: "z", subject: "run_command" }),
    ])
    const reader = auditFatigueReader(store)
    const result = await reader.readRecent(60_000)
    expect(result.map(e => e.tool_name)).toEqual(["send_email", "read_file", "run_command"])
  })
})