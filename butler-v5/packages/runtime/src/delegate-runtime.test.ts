import { describe, expect, it, vi } from "vitest"
import { delegate, type Capability } from "./delegate-runtime.js"
import type { EventBridge } from "@butler/persistence/event-bridge.js"

describe("delegate", () => {
  const caps: Capability[] = [
    { tool: "read_file" as Capability["tool"] },
    { tool: "search_project_knowledge" as Capability["tool"] },
  ]

  function makeBridgeMock() {
    return {
      appendConversationEventWithOutbox: vi.fn(async () => "msg-1"),
    } as unknown as EventBridge
  }

  it("writes a ChildRunCreated event and an outbox message; returns child metadata", async () => {
    const bridge = makeBridgeMock()
    const out = await delegate({
      role: "researcher",
      task: "find docs about Foo",
      capabilities: caps,
      parentConversationId: "p-1",
      actor: { kind: "agent", id: "kernel" },
      bridge,
    })
    expect(out.role).toBe("researcher")
    expect(out.capabilities).toEqual(caps)
    expect(out.parentConversationId).toBe("p-1")
    expect(out.childConversationId.startsWith("child-p-1-")).toBe(true)
    expect(out.childRunId).toBeNull()
    expect(bridge.appendConversationEventWithOutbox as ReturnType<typeof vi.fn>).toHaveBeenCalledTimes(1)
  })

  it("rejects empty capability list", async () => {
    const bridge = makeBridgeMock()
    await expect(
      delegate({
        role: "researcher",
        task: "x",
        capabilities: [],
        parentConversationId: "p-1",
        actor: { kind: "agent", id: "kernel" },
        bridge,
      }),
    ).rejects.toThrow(/capabilities/i)
    expect(bridge.appendConversationEventWithOutbox as ReturnType<typeof vi.fn>).not.toHaveBeenCalled()
  })

  it("passes capabilities through to the event payload", async () => {
    const bridge = makeBridgeMock()
    await delegate({
      role: "researcher",
      task: "summarize",
      capabilities: caps,
      parentConversationId: "p-2",
      actor: { kind: "agent", id: "kernel" },
      bridge,
    })
    const calls = (bridge.appendConversationEventWithOutbox as ReturnType<typeof vi.fn>).mock.calls
    expect(calls.length).toBe(1)
    const input = calls[0]?.[0]
    expect(input?.event).toMatchObject({
      _tag: "ChildRunCreated",
      role: "researcher",
      capabilities: caps,
    })
  })

  it("creates a relational Child Run when parentRunId + runtimeStore are provided", async () => {
    const { createRuntimeStore } = await import("@butler/persistence/runtime-store.js")
    const { makeTestDb } = await import("@butler/persistence/testing.js")
    const db = await makeTestDb()
    try {
      const store = createRuntimeStore(db.db)
      const createdAt = new Date("2026-08-20T00:00:00Z")
      const inbound = await store.createConversationWithUserMessage({
        conversationId: "parent-conv-a5",
        messageId: crypto.randomUUID(),
        subject: "owner-1",
        content: { text: "parent" },
        triggerSource: "channel",
        idempotencyKey: "a5-parent-msg",
        createdAt,
      })
      const parent = await store.createRun({
        id: crypto.randomUUID(),
        conversationId: inbound.conversationId,
        parentRunId: null,
        triggerSource: "channel",
        idempotencyKey: "a5-parent-run",
        subject: "owner-1",
        goal: "reply",
        budget: { maxSteps: 5 },
        deadline: null,
        createdAt,
      })
      await store.transitionRunStatus(parent.id, parent.version, "running", createdAt)
      const bridge = makeBridgeMock()
      const out = await delegate({
        role: "researcher",
        task: "find docs",
        capabilities: [{ tool: "general" as Capability["tool"] }],
        parentConversationId: inbound.conversationId,
        actor: { kind: "agent", id: "kernel" },
        bridge,
        runtimeStore: store,
        parentRunId: parent.id,
        subject: "owner-1",
      })
      expect(out.childRunId).toBeTruthy()
      if (!out.childRunId) throw new Error("expected childRunId")
      const child = await store.getRun(out.childRunId)
      expect(child?.parentRunId).toBe(parent.id)
      expect(child?.triggerSource).toBe("parent_run")
      expect(child?.status).toBe("queued")
      expect(child?.conversationId).toBe(out.childConversationId)
      const calls = (bridge.appendConversationEventWithOutbox as ReturnType<typeof vi.fn>).mock
        .calls
      expect(calls[0]?.[0]?.outbox?.payload).toMatchObject({
        childRunId: out.childRunId,
        parentRunId: parent.id,
      })
    } finally {
      await db.close()
    }
  })
})
