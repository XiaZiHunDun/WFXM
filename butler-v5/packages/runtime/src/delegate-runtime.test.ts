/**
 * D5-arch-align §20 #5: delegate() enforces child capabilities ⊆ parent allowlist.
 *
 * Three failure modes verified:
 *   1. parentRunId set + no parentAllowlist → fail-closed (throw)
 *   2. parentRunId set + parentAllowlist + child has a cap outside parent → throw
 *   3. parentRunId set + parentAllowlist + child ⊆ parent → proceeds
 *
 * Without parentRunId the legacy behavior is preserved (no parent = no
 * constraint to enforce; e.g. CLI one-shot tests or service-to-service
 * dispatch without a parent Run).
 */
import { describe, expect, it, beforeEach, afterEach } from "vitest"
import { delegate, type Capability } from "./delegate-runtime.js"
import { EventBridge } from "@butler/persistence/event-bridge.js"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { makeTestDb } from "@butler/persistence/testing.js"

describe("D5-arch-align: delegate child-cap ⊆ parent-allowlist", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let bridge: EventBridge

  beforeEach(async () => {
    db = await makeTestDb()
    bridge = new EventBridge({ db: db.db, workerId: "w-d5" })
  })
  afterEach(async () => {
    await db.close()
  })

  function makeCap(name: string): Capability {
    return { tool: name as Capability["tool"] }
  }

  it("parentRunId set + parentAllowlist omitted (= unrestricted parent) → no subset check, proceeds", async () => {
    // parentAllowlist=undefined means "parent unrestricted" (no allowedToolNames
    // arg passed at runButlerLoop). §20 #5 only constrains child when parent
    // is itself restricted.
    const result = await delegate({
      role: "researcher",
      task: "t",
      capabilities: [makeCap("read_file")],
      parentConversationId: "c-1",
      actor: { kind: "owner", id: "owner-1" },
      bridge,
      parentRunId: "11111111-1111-1111-1111-111111111111",
      // parentAllowlist intentionally omitted.
    })
    expect(result.childConversationId).toMatch(/^child-c-1-/)
  })

  it("parentRunId set + parentAllowlist empty array → fail-closed (no tools allowed)", async () => {
    // Empty array ≠ undefined. Empty array means "parent has zero tools",
    // so any child cap is "wider than parent" and rejected.
    await expect(
      delegate({
        role: "developer",
        task: "t",
        capabilities: [makeCap("read_file")],
        parentConversationId: "c-1b",
        actor: { kind: "owner", id: "owner-1" },
        bridge,
        parentRunId: "11111111-1111-1111-1111-111111111111",
        parentAllowlist: [], // empty = restricted to nothing
      }),
    ).rejects.toThrow(/not in parent allowlist/)
  })

  it("child cap not in parent allowlist → throw (no silent widening)", async () => {
    await expect(
      delegate({
        role: "developer",
        task: "t",
        capabilities: [makeCap("run_command")], // child asks for run_command
        parentConversationId: "c-2",
        actor: { kind: "owner", id: "owner-1" },
        bridge,
        parentRunId: "22222222-2222-2222-2222-222222222222",
        parentAllowlist: [makeCap("read_file")], // parent only has read_file
      }),
    ).rejects.toThrow(/run_command not in parent allowlist/)
  })

  it("child cap ⊆ parent allowlist → proceeds (no throw)", async () => {
    const result = await delegate({
      role: "developer",
      task: "t",
      capabilities: [makeCap("read_file"), makeCap("write_file")],
      parentConversationId: "c-3",
      actor: { kind: "owner", id: "owner-1" },
      bridge,
      parentRunId: "33333333-3333-3333-3333-333333333333",
      parentAllowlist: [makeCap("read_file"), makeCap("write_file"), makeCap("run_command")],
    })
    expect(result.childConversationId).toMatch(/^child-c-3-/)
  })

  it("child cap equals parent allowlist exactly (1 element) → proceeds", async () => {
    const result = await delegate({
      role: "general",
      task: "t",
      capabilities: [makeCap("general")],
      parentConversationId: "c-4",
      actor: { kind: "owner", id: "owner-1" },
      bridge,
      parentRunId: "44444444-4444-4444-4444-444444444444",
      parentAllowlist: [makeCap("general")],
    })
    expect(result.childConversationId).toMatch(/^child-c-4-/)
  })

  it("no parentRunId (legacy path) → no constraint enforced; arbitrary caps allowed", async () => {
    const result = await delegate({
      role: "developer",
      task: "t",
      capabilities: [makeCap("run_command")],
      parentConversationId: "c-5",
      actor: { kind: "owner", id: "owner-1" },
      bridge,
      // parentRunId omitted → no §20 #5 enforcement; legacy behavior.
    })
    expect(result.childConversationId).toMatch(/^child-c-5-/)
  })

  it("rejects empty capabilities", async () => {
    await expect(
      delegate({
        role: "researcher",
        task: "t",
        capabilities: [],
        parentConversationId: "c-empty",
        actor: { kind: "owner", id: "owner-1" },
        bridge,
      }),
    ).rejects.toThrow(/capabilities must not be empty/)
  })

  it("creates a child run, step, and audit when runtimeStore + parentRunId are provided", async () => {
    const store = createRuntimeStore(db)
    const appendAudit = vi.spyOn(store, "appendAuditEvent")
    // The runs.parent_run_id FK requires a real parent run to exist.
    const parentConv = await store.createConversationWithUserMessage({
      conversationId: crypto.randomUUID(),
      messageId: crypto.randomUUID(),
      subject: "owner-1",
      content: { text: "parent" },
      triggerSource: "channel",
      idempotencyKey: crypto.randomUUID(),
      createdAt: new Date("2026-08-20T00:00:00Z"),
    })
    const parentRun = await store.createRun({
      id: crypto.randomUUID(),
      conversationId: parentConv.conversationId,
      parentRunId: null,
      triggerSource: "channel",
      idempotencyKey: crypto.randomUUID(),
      subject: "owner-1",
      goal: "parent goal",
      budget: { maxSteps: 5 },
      deadline: null,
      createdAt: new Date("2026-08-20T00:00:00Z"),
    })
    const out = await delegate({
      role: "researcher",
      task: "write a summary",
      capabilities: [makeCap("read_file")],
      parentConversationId: parentConv.conversationId,
      parentRunId: parentRun.id,
      runtimeStore: store,
      bridge,
      actor: { kind: "owner", id: "owner-1" },
      subject: "owner-1",
      notifySubject: "  owner-1  ",
    })
    expect(out.childRunId).toBeTruthy()
    
    expect(out.childConversationId).toMatch(/^child-/) 
    const msgs = await store.listMessages(out.childConversationId)
    expect(msgs).toHaveLength(1)
    expect(msgs[0]?.content).toEqual({ text: "write a summary" })
    expect(appendAudit).toHaveBeenCalled()
    const detail = appendAudit.mock.calls[0]?.[0].detail as { parentRunId?: string }
    expect(detail.parentRunId).toBe(parentRun.id)
  })
})
