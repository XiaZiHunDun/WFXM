import { mkdtempSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { Hono } from "hono"
import { makeTestDb } from "@butler/persistence/testing.js"
import { EventBridge } from "@butler/persistence/event-bridge.js"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import { createProjectKnowledgeStore, createTaskStore } from "@butler/persistence"
import { createRoutes } from "./routes.js"
import { makeWiring, type Wiring } from "./wiring.js"
import { readWechatSessionState } from "./wechat-session-state.js"

describe("HTTP API routes", () => {
  it("GET /healthz returns 200 OK", async () => {
    const app = new Hono()
    createRoutes(app, { eventStore: null as never })
    const res = await app.request("/healthz")
    expect(res.status).toBe(200)
    const body = (await res.json()) as { status: string }
    expect(body.status).toBe("ok")
  })

  it("POST /v1/conversations requires body", async () => {
    const app = new Hono()
    createRoutes(app, { eventStore: null as never })
    const res = await app.request("/v1/conversations", { method: "POST" })
    expect(res.status).toBe(400)
  })
})

describe("B 方向: session snapshot capture on inbound", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let wiring: Wiring
  let storeDir = ""
  let env: NodeJS.ProcessEnv

  beforeEach(async () => {
    db = await makeTestDb()
    const bridge = new EventBridge({ db: db.db, workerId: "routes-session-test" })
    wiring = makeWiring({
      bridge,
      workerId: "routes-session-test",
      runtimeStore: createRuntimeStore(db.db),
      runEngine: new RunEngine(createRuntimeStore(db.db)),
      db: db.db,
      backfillConversation: async () => undefined,
      projectKnowledgeStore: createProjectKnowledgeStore(db.db),
      taskStore: createTaskStore(db.db),
    })
    storeDir = mkdtempSync(join(tmpdir(), "butler-routes-session-"))
    env = {
      BUTLER_V5_WECHAT_ACTIVE_PROJECT_STORE: join(storeDir, "active.json"),
      BUTLER_V5_PROJECT_KNOWLEDGE_INBOUND_MAP: "wechat:WFXM",
      BUTLER_V5_WECHAT_TOOL_ALLOWLIST_PATH: join(process.cwd(), "config/wechat-tool-allowlist.json"),
      BUTLER_V5_WECHAT_PROJECT_PATHS: join(process.cwd(), "config/wechat-project-paths.json"),
      BUTLER_V5_WECHAT_SESSION_STATE: join(storeDir, "session.json"),
      BUTLER_V5_WORKSPACE_ROOT: join(process.cwd(), ".."),
    }
  })

  afterEach(async () => {
    await db.close()
    if (storeDir) rmSync(storeDir, { recursive: true, force: true })
  })

  it("slash command path captures a snapshot (lastRunStatus=none)", async () => {
    const app = new Hono()
    // Inject env via process.env so the route handler reads it
    const origEnv = { ...process.env }
    Object.assign(process.env, env)
    try {
      createRoutes(app, wiring)
      const res = await app.request("/v1/wechat/inbound", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          apiVersion: "v1",
          fromUserId: "u-routes-1",
          content: "/状态",
        }),
      })
      expect(res.status).toBe(201)
      // Snapshot file should now exist for this user
      const state = readWechatSessionState("u-routes-1", env)
      expect(state).not.toBeNull()
      expect(state?.lastRunStatus).toBe("none")
      expect(state?.openTaskCount).toBe(0)
    } finally {
      process.env = origEnv
    }
  })

  it("snapshot is keyed per user (multi-user isolation through routes)", async () => {
    const app = new Hono()
    const origEnv = { ...process.env }
    Object.assign(process.env, env)
    try {
      createRoutes(app, wiring)
      await app.request("/v1/wechat/inbound", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          apiVersion: "v1",
          fromUserId: "u-iso-A",
          content: "/状态",
        }),
      })
      await app.request("/v1/wechat/inbound", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          apiVersion: "v1",
          fromUserId: "u-iso-B",
          content: "/状态",
        }),
      })
      expect(readWechatSessionState("u-iso-A", env)).not.toBeNull()
      expect(readWechatSessionState("u-iso-B", env)).not.toBeNull()
    } finally {
      process.env = origEnv
    }
  })
})
