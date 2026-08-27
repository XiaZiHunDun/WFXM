import { mkdtempSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { describe, expect, it, afterEach, beforeEach } from "vitest"
import { makeTestDb } from "@butler/persistence/testing.js"
import { EventBridge } from "@butler/persistence/event-bridge.js"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import { makeWiring, type Wiring } from "./wiring.js"
import { appendAudit } from "./audit-log.js"
import { tryWechatSubagentCommand } from "./wechat-subagent-commands.js"

describe("wechat subagent commands", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let wiring: Wiring
  let testEnv: NodeJS.ProcessEnv
  let storeDir = ""

  beforeEach(async () => {
    db = await makeTestDb()
    const bridge = new EventBridge({ db: db.db, workerId: "subagent-cmd" })
    wiring = makeWiring({
      bridge,
      workerId: "subagent-cmd",
      runtimeStore: createRuntimeStore(db.db),
      runEngine: new RunEngine(createRuntimeStore(db.db)),
      db: db.db,
      backfillConversation: async () => undefined,
    })
    storeDir = mkdtempSync(join(tmpdir(), "butler-subagent-cmd-"))
    process.env["BUTLER_V5_SUBAGENT_AUDIT_PATH"] = join(storeDir, "subagent.jsonl")
    testEnv = {
      BUTLER_V5_WECHAT_ACTIVE_PROJECT_STORE: join(storeDir, "active.json"),
      BUTLER_V5_SUBAGENT_ENABLED: "1",
      BUTLER_V5_SUBAGENT_AUDIT_PATH: join(storeDir, "subagent.jsonl"),
    }
  })

  afterEach(async () => {
    delete process.env["BUTLER_V5_SUBAGENT_AUDIT_PATH"]
    await db.close()
    rmSync(storeDir, { recursive: true, force: true })
  })

  it("shows usage for bare /委派", async () => {
    const result = await tryWechatSubagentCommand({
      wiring,
      fromUserId: "u-sub",
      content: "/委派",
      env: testEnv,
    })
    expect(result?.reply).toContain("用法")
  })

  it("shows recent delegations from audit log", async () => {
    appendAudit({
      ts: new Date().toISOString(),
      kind: "delegation",
      parentConversationId: "c-wechat-u-sub",
      childConversationId: "child-c-wechat-u-sub-1",
      role: "general",
      task: "smoke summary",
      capabilities: ["general"],
    })
    const status = await tryWechatSubagentCommand({
      wiring,
      fromUserId: "u-sub",
      content: "/委派状态",
      env: testEnv,
    })
    expect(status?.reply).toContain("最近委派")
    expect(status?.reply).toContain("smoke")
  })
})
