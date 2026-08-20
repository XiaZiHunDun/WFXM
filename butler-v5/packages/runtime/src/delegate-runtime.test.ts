import { describe, expect, it, vi } from "vitest"
import { delegate, type Capability } from "./delegate-runtime.js"
import type { EventBridge } from "./bridge.js"

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
})
