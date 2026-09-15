import { describe, expect, it, vi, beforeEach, afterEach } from "vitest"
import type { AuditEventRecord, RuntimeStore } from "@butler/domain/runtime.js"
import { listRecentAuditEvents, writeSubagentAudit } from "./audit-service.js"

interface CapturedEvent {
  readonly action: string
  readonly subject: string
  readonly conversationId: string | null
}

function makeStore(opts: {
  appendImpl?: (input: {
    auditId: string
    runId: string | null
    conversationId: string | null
    action: string
    subject: string
    detail: Readonly<Record<string, unknown>>
    createdAt: Date
  }) => Promise<void>
}): {
  store: RuntimeStore
  events: CapturedEvent[]
} {
  const events: CapturedEvent[] = []
  const appendImpl =
    opts.appendImpl ??
    (async (input) => {
      events.push({ action: input.action, subject: input.subject, conversationId: input.conversationId })
    })
  const store = {
    appendAuditEvent: appendImpl,
  } as unknown as RuntimeStore
  return { store, events }
}

const baseEntry = {
  ts: new Date().toISOString(),
  kind: "delegation" as const,
  parentConversationId: "parent-conv-1",
  childConversationId: "child-conv-1",
  role: "general",
  task: "do the thing",
  capabilities: ["general"],
}

describe("writeSubagentAudit", () => {
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {})
  })

  afterEach(() => {
    consoleErrorSpy.mockRestore()
  })

  it("uses entry.ownerSubject as audit_events.subject when provided", async () => {
    const { store, events } = makeStore({})
    const pending = new Promise<void>((resolve) => {
      // wait one microtask so we can observe after the .catch resolves
      setImmediate(resolve)
    })
    writeSubagentAudit(store, {
      ...baseEntry,
      ownerSubject: "owner-wechat-id-7",
    })
    await pending
    // Drain the implicit promise queue so the .catch arm runs.
    await new Promise((r) => setImmediate(r))
    expect(events).toHaveLength(1)
    expect(events[0]?.subject).toBe("owner-wechat-id-7")
    expect(events[0]?.action).toBe("subagent.delegation")
  })

  it("falls back to entry.role when ownerSubject is absent (back-compat)", async () => {
    const { store, events } = makeStore({})
    writeSubagentAudit(store, { ...baseEntry })
    await new Promise((r) => setImmediate(r))
    expect(events).toHaveLength(1)
    expect(events[0]?.subject).toBe("general")
  })

  it("logs to console.error when appendAuditEvent rejects (observability)", async () => {
    const store = makeStore({
      appendImpl: async () => {
        throw new Error("pglite: schema_mismatch")
      },
    }).store
    writeSubagentAudit(store, {
      ...baseEntry,
      ownerSubject: "owner-x",
    })
    // Wait long enough for the rejected promise's .catch handler to run.
    await new Promise((r) => setImmediate(r))
    await new Promise((r) => setImmediate(r))
    expect(consoleErrorSpy).toHaveBeenCalled()
    const firstCall = consoleErrorSpy.mock.calls[0]
    expect(String(firstCall?.[0] ?? "")).toContain("audit-service")
    expect(String(firstCall?.[0] ?? "")).toContain("appendAuditEvent")
  })

  it("does not throw when store is undefined", () => {
    expect(() => writeSubagentAudit(undefined, { ...baseEntry })).not.toThrow()
  })
})

/** D66 T1a helper: build a minimal AuditEventRecord for mock-store returns. */
function makeAuditEvent(overrides: {
  auditId: string
  subject: string
  conversationId?: string | null
  createdAt?: Date
}): AuditEventRecord {
  return {
    auditId: overrides.auditId,
    runId: null,
    conversationId: overrides.conversationId ?? null,
    action: "subagent.delegation",
    subject: overrides.subject,
    detail: {},
    createdAt: overrides.createdAt ?? new Date("2026-09-15T00:00:00.000Z"),
    correlationId: null,
  }
}

function makeListStore(
  impl: (input: {
    readonly actor?: string
    readonly windowMs: number
    readonly conversationId?: string
    readonly limit?: number
  }) => Promise<readonly AuditEventRecord[]>,
): { store: RuntimeStore; list: ReturnType<typeof vi.fn> } {
  const list = vi.fn(impl)
  const store = { listRecentAuditEvents: list } as unknown as RuntimeStore
  return { store, list }
}

describe("listRecentAuditEvents", () => {
  it("L1: actor filter returns only events matching the requested subject", async () => {
    // Mock the store to mirror the production filter semantics: when actor
    // is supplied, only events with the same `subject` come back.
    const allEvents: readonly AuditEventRecord[] = [
      makeAuditEvent({ auditId: "a1", subject: "owner-1" }),
      makeAuditEvent({ auditId: "a2", subject: "owner-2" }),
      makeAuditEvent({ auditId: "a3", subject: "owner-1" }),
    ]
    const { store, list } = makeListStore(async (input) =>
      input.actor === undefined
        ? allEvents
        : allEvents.filter((e) => e.subject === input.actor),
    )

    const result = await listRecentAuditEvents(store, {
      actor: "owner-1",
      windowMs: 60_000,
    })

    expect(list).toHaveBeenCalledTimes(1)
    expect(list).toHaveBeenCalledWith({ actor: "owner-1", windowMs: 60_000 })
    expect(result).toHaveLength(2)
    expect(result.every((e) => e.subject === "owner-1")).toBe(true)
    expect(result.map((e) => e.auditId).sort()).toEqual(["a1", "a3"])
  })

  it("L2: windowMs filter returns only events within the recency window", async () => {
    // Mock the store to apply the windowMs cutoff at call time.
    const now = Date.now()
    const recent = makeAuditEvent({
      auditId: "recent",
      subject: "owner-1",
      createdAt: new Date(now - 5_000),
    })
    const stale = makeAuditEvent({
      auditId: "stale",
      subject: "owner-1",
      createdAt: new Date(now - 120_000),
    })
    const { store, list } = makeListStore(async (input) => {
      const cutoff = Date.now() - input.windowMs
      return [recent, stale].filter((e) => e.createdAt.getTime() >= cutoff)
    })

    const result = await listRecentAuditEvents(store, { windowMs: 60_000 })

    expect(list).toHaveBeenCalledWith({ windowMs: 60_000 })
    expect(result.map((e) => e.auditId)).toEqual(["recent"])
  })

  it("L3: limit caps the returned events", async () => {
    // Mock the store to apply the limit at the tail (production orders
    // newest-first, so we slice the head).
    const events: readonly AuditEventRecord[] = Array.from({ length: 10 }, (_, i) =>
      makeAuditEvent({ auditId: `a${i}`, subject: "owner-1" }),
    )
    const { store, list } = makeListStore(async (input) =>
      input.limit === undefined ? events : events.slice(0, input.limit),
    )

    const result = await listRecentAuditEvents(store, {
      windowMs: 60_000,
      limit: 5,
    })

    expect(list).toHaveBeenCalledWith({ windowMs: 60_000, limit: 5 })
    expect(result).toHaveLength(5)
  })

  it("L4: empty store returns an empty array", async () => {
    const { store, list } = makeListStore(async () => [])

    const result = await listRecentAuditEvents(store, { windowMs: 60_000 })

    expect(list).toHaveBeenCalledTimes(1)
    expect(result).toEqual([])
  })
})
