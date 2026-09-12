import { describe, expect, it, vi, beforeEach, afterEach } from "vitest"
import type { RuntimeStore } from "@butler/domain/runtime.js"
import { writeSubagentAudit } from "./audit-service.js"

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
