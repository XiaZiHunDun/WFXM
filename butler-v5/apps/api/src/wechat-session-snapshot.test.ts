import { mkdtempSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { makeTestDb } from "@butler/persistence/testing.js"
import { EventBridge } from "@butler/persistence/event-bridge.js"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import {
  createDurableMemoryStore,
  createTaskStore,
} from "@butler/persistence"
import { makeWiring, type Wiring } from "./wiring.js"
import { captureWechatSessionSnapshot } from "./wechat-session-snapshot.js"
import { readWechatSessionState } from "./wechat-session-state.js"

describe("captureWechatSessionSnapshot", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let wiring: Wiring
  let storeDir = ""
  let env: NodeJS.ProcessEnv

  beforeEach(async () => {
    db = await makeTestDb()
    const bridge = new EventBridge({ db: db.db, workerId: "snapshot-test" })
    wiring = makeWiring({
      bridge,
      workerId: "snapshot-test",
      runtimeStore: createRuntimeStore(db.db),
      runEngine: new RunEngine(createRuntimeStore(db.db)),
      db: db.db,
      backfillConversation: async () => undefined,
      taskStore: createTaskStore(db.db),
      durableMemoryStore: createDurableMemoryStore(db.db),
    })
    storeDir = mkdtempSync(join(tmpdir(), "butler-session-snap-"))
    env = { BUTLER_V5_WECHAT_SESSION_STATE: join(storeDir, "session.json") }
  })

  afterEach(async () => {
    await db.close()
    if (storeDir) rmSync(storeDir, { recursive: true, force: true })
  })

  it("captures zero open tasks and zero candidates on a fresh user", async () => {
    await captureWechatSessionSnapshot({
      wiring,
      userId: "u-snap",
      env,
      now: 1_000_000,
    })
    const s = readWechatSessionState("u-snap", env)
    expect(s?.openTaskCount).toBe(0)
    expect(s?.candidateCount).toBe(0)
    expect(s?.lastReplyAt).toBe(1_000_000)
  })

  it("lastRunStatus='none' when no runResult is passed (slash path)", async () => {
    await captureWechatSessionSnapshot({
      wiring,
      userId: "u-snap",
      env,
      now: 1_000_000,
    })
    expect(readWechatSessionState("u-snap", env)?.lastRunStatus).toBe("none")
  })

  it("lastRunStatus='success' when runResult has no failure trace", async () => {
    await captureWechatSessionSnapshot({
      wiring,
      userId: "u-snap",
      env,
      now: 1_000_000,
      runResult: { traces: ["intake:dev_task", "llm_call:plan:1"], finalDecision: "Respond" },
    })
    expect(readWechatSessionState("u-snap", env)?.lastRunStatus).toBe("success")
  })

  it("lastRunStatus='fail' when runResult has failure trace", async () => {
    await captureWechatSessionSnapshot({
      wiring,
      userId: "u-snap",
      env,
      now: 1_000_000,
      runResult: { traces: ["intake:dev_task", "llm_call:error"], finalDecision: "Respond" },
    })
    expect(readWechatSessionState("u-snap", env)?.lastRunStatus).toBe("fail")
  })

  it("graceful: missing task store → openTaskCount stays null", async () => {
    const wiringNoTask: Wiring = { ...wiring, taskStore: null }
    await captureWechatSessionSnapshot({
      wiring: wiringNoTask,
      userId: "u-snap",
      env,
      now: 1_000_000,
    })
    expect(readWechatSessionState("u-snap", env)?.openTaskCount).toBeNull()
    expect(readWechatSessionState("u-snap", env)?.candidateCount).toBe(0)
  })

  it("graceful: empty userId short-circuits without writing", async () => {
    await captureWechatSessionSnapshot({
      wiring,
      userId: "   ",
      env,
      now: 1_000_000,
    })
    expect(readWechatSessionState("   ", env)).toBeNull()
  })
})
