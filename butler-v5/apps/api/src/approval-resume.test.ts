import { describe, expect, it, beforeEach, afterEach } from "vitest"
import { eq } from "drizzle-orm"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { runs, steps } from "@butler/persistence/schema.js"
import { makeTestDb } from "@butler/persistence/testing.js"
import {
  approveWaitingStep,
  createWaitingApprovalStep,
} from "@butler/runtime/approval-runtime.js"
import { EventBridge } from "@butler/runtime/bridge.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import { resumeApprovedCapability } from "./approval-resume.js"
import { makeWiring } from "./wiring.js"

describe("resumeApprovedCapability (A1 same-Run resume)", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>

  beforeEach(async () => {
    db = await makeTestDb()
  })

  afterEach(async () => {
    await db.close()
  })

  it("resumes the same runId, records capability Step, and does not createRun", async () => {
    const runtimeStore = createRuntimeStore(db.db)
    const wiring = makeWiring({
      bridge: new EventBridge({ db: db.db, workerId: "a1-test" }),
      workerId: "a1-test",
      runtimeStore,
      runEngine: new RunEngine(runtimeStore),
      db: db.db,
      backfillConversation: async () => undefined,
    })
    const createdAt = new Date("2026-08-20T00:00:00Z")
    const conversationId = "conv-a1-resume"
    await runtimeStore.createConversationWithUserMessage({
      conversationId,
      messageId: crypto.randomUUID(),
      subject: "owner-1",
      content: { text: "send" },
      triggerSource: "channel",
      idempotencyKey: "a1-msg",
      createdAt,
    })
    const run = await runtimeStore.createRun({
      id: crypto.randomUUID(),
      conversationId,
      parentRunId: null,
      triggerSource: "channel",
      idempotencyKey: "a1-run",
      subject: "owner-1",
      goal: "reply",
      budget: { maxSteps: 5 },
      deadline: null,
      createdAt,
    })
    await runtimeStore.transitionRunStatus(run.id, run.version, "running", createdAt)
    const { stepId } = await createWaitingApprovalStep(runtimeStore, {
      runId: run.id,
      conversationId,
      subject: "owner-1",
      capability: "get_current_time",
      resource: conversationId,
      args: {},
      question: "Confirm?",
      expiresAtMs: Date.now() + 60_000,
      digest: "a1-digest",
      kind: "read",
      risk: "low",
    })
    const decision = await approveWaitingStep(runtimeStore, stepId, "owner-1")
    const result = await resumeApprovedCapability(wiring, decision, {
      env: {
        ...process.env,
        OPENAI_API_KEY: "",
        ANTHROPIC_API_KEY: "",
        MINIMAX_API_KEY: "",
      },
    })
    expect(result.ok).toBe(true)
    if (result.ok) expect(String(result.output).length).toBeGreaterThan(0)

    const updated = await runtimeStore.getRun(run.id)
    expect(updated?.status).toBe("succeeded")

    const allRuns = await db.db.select().from(runs).where(eq(runs.conversationId, conversationId))
    expect(allRuns).toHaveLength(1)
    expect(allRuns[0]?.runId).toBe(run.id)

    const runSteps = await db.db.select().from(steps).where(eq(steps.runId, run.id))
    expect(runSteps.some((s) => s.kind === "approval")).toBe(true)
    expect(runSteps.some((s) => s.kind === "capability")).toBe(true)
    const resultStep = runSteps.find((s) => s.kind === "result")
    expect(resultStep).toBeTruthy()
    const input = resultStep?.input as { source?: string } | null
    expect(input?.source === "tool_fallback" || input?.source === "conversation_loop").toBe(true)
  })
})
