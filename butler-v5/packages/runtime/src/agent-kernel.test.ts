import { describe, expect, it, beforeEach, afterEach } from "vitest"
import { EventBridge } from "./bridge.js"
import { AgentKernel } from "./agent-kernel.js"
import { makeTestDb } from "@butler/persistence/testing.js"

describe("AgentKernel", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let bridge: EventBridge
  let kernel: AgentKernel

  beforeEach(async () => {
    db = await makeTestDb()
    bridge = new EventBridge({ db: db.db, workerId: "w-1" })
    kernel = new AgentKernel({
      bridge,
      conversationId: "c-1",
      projectId: "p-1",
      actor: { kind: "system", id: "kernel" },
    })
  })

  afterEach(async () => {
    await db.close()
  })

  it("starts in Idle state", () => {
    expect(kernel.state).toBe("idle")
  })

  it("transitions Idle → running → completed for a Respond decision", async () => {
    await kernel.openTurn({ userMessage: { role: "user", content: "hi" } })
    expect(kernel.state).toBe("running")
    await kernel.applyDecision({ _tag: "Respond", content: "hello" })
    expect(kernel.state).toBe("completed")
    const events = await bridge.loadStream("c-1")
    expect(events.length).toBeGreaterThan(0)
  })

  it("transitions to tooling for CallTool decisions", async () => {
    await kernel.openTurn({ userMessage: { role: "user", content: "x" } })
    await kernel.applyDecision({
      _tag: "CallTool",
      toolName: "read_file",
      args: { path: "/ws" },
    })
    expect(kernel.state).toBe("tooling")
  })

  it("transitions to waiting_approval for AskApproval decisions", async () => {
    await kernel.openTurn({ userMessage: { role: "user", content: "x" } })
    await kernel.applyDecision({ _tag: "AskApproval", question: "ok?" })
    expect(kernel.state).toBe("waiting_approval")
  })

  it("transitions to delegating for Delegate decisions", async () => {
    await kernel.openTurn({ userMessage: { role: "user", content: "x" } })
    await kernel.applyDecision({ _tag: "Delegate", role: "researcher", task: "find docs" })
    expect(kernel.state).toBe("delegating")
  })

  it("transitions to completed for Finish decisions", async () => {
    await kernel.openTurn({ userMessage: { role: "user", content: "x" } })
    await kernel.applyDecision({ _tag: "Finish", reason: "done" })
    expect(kernel.state).toBe("completed")
  })

  it("rejects openTurn on completed conversation", async () => {
    await kernel.openTurn({ userMessage: { role: "user", content: "x" } })
    await kernel.applyDecision({ _tag: "Finish", reason: "ok" })
    await expect(kernel.openTurn({ userMessage: { role: "user", content: "y" } })).rejects.toThrow(
      /completed/i,
    )
  })
})
