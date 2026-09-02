import { describe, expect, it, vi } from "vitest"
import type { RuntimeStore } from "@butler/domain/runtime.js"
import { recordExecAudit, type ExecAuditRecord } from "./exec-audit.js"

function makeStore(): {
  store: RuntimeStore
  events: {
    auditId: string
    runId: string | null
    conversationId: string | null
    action: string
    subject: string
    detail: Readonly<Record<string, unknown>>
    createdAt: Date
  }[]
} {
  const events: {
    auditId: string
    runId: string | null
    conversationId: string | null
    action: string
    subject: string
    detail: Readonly<Record<string, unknown>>
    createdAt: Date
  }[] = []
  const appendAuditEvent = vi.fn(
    async (input: (typeof events)[number]): Promise<void> => {
      events.push(input)
    },
  )
  const store = { appendAuditEvent } as unknown as RuntimeStore
  return { store, events }
}

const sampleRecord: ExecAuditRecord = {
  cmd: "cat -- /tmp/a.txt",
  cwd: "/workspace",
  exit: 0,
  durationMs: 42,
  outcome: "ok",
}

describe("recordExecAudit", () => {
  it("is a no-op (resolves, calls nothing) when no context is wired", async () => {
    await expect(recordExecAudit(undefined, sampleRecord)).resolves.toBeUndefined()
    // ctx without a runtimeStore is also a no-op
    await expect(recordExecAudit({}, sampleRecord)).resolves.toBeUndefined()
  })

  it("appends one exec.executed event with the expected shape", async () => {
    const { store, events } = makeStore()
    await recordExecAudit({ runtimeStore: store }, sampleRecord)

    expect(events).toHaveLength(1)
    const event = events[0]
    expect(event.action).toBe("exec.executed")
    expect(event.runId).toBeNull()
    expect(event.conversationId).toBeNull()
    expect(event.subject).toBe("system")
    expect(event.auditId).toMatch(/^[0-9a-f-]{36}$/u)
    expect(event.createdAt).toBeInstanceOf(Date)
    expect(event.detail).toEqual({
      kind: "exec",
      cmd: "cat -- /tmp/a.txt",
      cwd: "/workspace",
      exit: 0,
      durationMs: 42,
      outcome: "ok",
    })
  })

  it("passes runId / conversationId / subject from the injected context", async () => {
    const { store, events } = makeStore()
    await recordExecAudit(
      {
        runtimeStore: store,
        runId: "run-1",
        conversationId: "conv-1",
        subject: "owner-u1",
      },
      sampleRecord,
    )
    expect(events[0]?.runId).toBe("run-1")
    expect(events[0]?.conversationId).toBe("conv-1")
    expect(events[0]?.subject).toBe("owner-u1")
  })

  it("merges record.detail onto the base exec detail", async () => {
    const { store, events } = makeStore()
    await recordExecAudit(
      { runtimeStore: store },
      { ...sampleRecord, detail: { tool: "run_command", kind: "mcp-server" } },
    )
    expect(events[0]?.detail).toEqual({
      kind: "mcp-server", // record.detail overrides the base kind
      cmd: "cat -- /tmp/a.txt",
      cwd: "/workspace",
      exit: 0,
      durationMs: 42,
      outcome: "ok",
      tool: "run_command",
    })
  })

  it("keeps null exit for spawned outcomes", async () => {
    const { store, events } = makeStore()
    await recordExecAudit(
      { runtimeStore: store },
      { cmd: "node", cwd: "/workspace", exit: null, durationMs: 0, outcome: "spawned" },
    )
    expect(events[0]?.detail?.exit).toBeNull()
    expect(events[0]?.detail?.outcome).toBe("spawned")
  })

  it("swallows append failures so audit never breaks the exec path", async () => {
    const store = {
      appendAuditEvent: vi.fn(async () => {
        throw new Error("db closed")
      }),
    } as unknown as RuntimeStore
    await expect(recordExecAudit({ runtimeStore: store }, sampleRecord)).resolves.toBeUndefined()
  })

  it("swallows synchronous errors from a partial store without appendAuditEvent", async () => {
    const partial = {} as unknown as RuntimeStore
    await expect(recordExecAudit({ runtimeStore: partial }, sampleRecord)).resolves.toBeUndefined()
  })
})
