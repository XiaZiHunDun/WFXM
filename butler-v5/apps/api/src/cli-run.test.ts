import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { eq } from "drizzle-orm"
import { EventBridge } from "@butler/persistence/event-bridge.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { runs } from "@butler/persistence/schema.js"
import { makeTestDb } from "@butler/persistence/testing.js"
import { makeWiring, type Wiring } from "./wiring.js"
import { defaultCliConversationId, runCliGoal } from "./cli-run.js"

describe("runCliGoal", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let wiring: Wiring

  beforeEach(async () => {
    db = await makeTestDb()
    const bridge = new EventBridge({ db: db.db, workerId: "w-cli" })
    const runtimeStore = createRuntimeStore(db.db)
    wiring = makeWiring({
      bridge,
      workerId: "w-cli",
      runtimeStore,
      runEngine: new RunEngine(runtimeStore),
      db: db.db,
      backfillConversation: async () => undefined,
    })
  })

  afterEach(async () => {
    await db.close()
  })

  it("builds stable cli conversation ids from goal text", () => {
    expect(defaultCliConversationId("owner-1", "hello")).toMatch(/^cli-owner-1-/)
  })

  it("persists cli RunTrigger metadata on inbound run", async () => {
    const goal = "what time is it"
    const subject = "cli-owner"
    const conversationId = defaultCliConversationId(subject, goal)
    await runCliGoal({
      wiring,
      goal,
      subject,
      conversationId,
      env: {},
    })
    const [run] = await db.select().from(runs).where(eq(runs.conversationId, conversationId))
    expect(run?.triggerSource).toBe("cli")
    expect(run?.budget).toMatchObject({
      trustLevel: "owner",
      triggerPayload: { goal },
    })
  })
})
