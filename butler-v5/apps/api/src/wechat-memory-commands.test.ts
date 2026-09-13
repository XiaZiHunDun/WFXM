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
  createProjectKnowledgeStore,
  createTaskStore,
  type DurableMemoryStore,
} from "@butler/persistence"
import { makeWiring, type Wiring } from "./wiring.js"
import { tryWechatMemoryCommand } from "./wechat-memory-commands.js"

describe("tryWechatMemoryCommand /记住", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let wiring: Wiring
  let testEnv: NodeJS.ProcessEnv
  let storeDir = ""

  beforeEach(async () => {
    db = await makeTestDb()
    const bridge = new EventBridge({ db: db.db, workerId: "memory-cmds-test" })
    wiring = makeWiring({
      bridge,
      workerId: "memory-cmds-test",
      runtimeStore: createRuntimeStore(db.db),
      runEngine: new RunEngine(createRuntimeStore(db.db)),
      db: db.db,
      backfillConversation: async () => undefined,
      projectKnowledgeStore: createProjectKnowledgeStore(db.db),
      taskStore: createTaskStore(db.db),
      durableMemoryStore: createDurableMemoryStore(db.db),
    })
    storeDir = mkdtempSync(join(tmpdir(), "butler-mem-cmd-"))
    testEnv = {
      BUTLER_V5_WECHAT_ACTIVE_PROJECT_STORE: join(storeDir, "active.json"),
      BUTLER_V5_PROJECT_KNOWLEDGE_INBOUND_MAP: "wechat:WFXM",
      BUTLER_V5_WECHAT_TOOL_ALLOWLIST_PATH: join(process.cwd(), "config/wechat-tool-allowlist.json"),
      BUTLER_V5_WECHAT_PROJECT_PATHS: join(process.cwd(), "config/wechat-project-paths.json"),
      BUTLER_V5_WORKSPACE_ROOT: join(process.cwd(), ".."),
      BUTLER_V5_MEMORY_DEDUP_ENABLED: "1",
    }
  })

  afterEach(async () => {
    await db.close()
    if (storeDir) rmSync(storeDir, { recursive: true, force: true })
  })

  it("surfaces dedup DB error to owner instead of silent fail-open (D55 SF-02)", async () => {
    // Audit finding (D55 SF-02): dedup check failure was stderr-only, owner
    // never knew dedup wasn't running. §20 #11 requires fail-open (write
    // must proceed), but owner must also see a warning so dedup outages
    // don't silently degrade into unbounded duplicates.
    const realStore = createDurableMemoryStore(db.db)
    const degradedStore: DurableMemoryStore = {
      ...realStore,
      findCandidatesForDedup: async () => {
        throw new Error("simulated dedup outage")
      },
    }
    const failWiring: Wiring = {
      ...wiring,
      durableMemoryStore: degradedStore,
    }
    const result = await tryWechatMemoryCommand({
      wiring: failWiring,
      fromUserId: "u-mem",
      content: "/记住 测试内容 dedup 应该 fail-open 但 owner 要知道",
      env: testEnv,
    })
    // Fail-open preserved: write still succeeded
    expect(result).not.toBeNull()
    if (result === null) return
    expect(result.reply).toContain("已记住")
    // D62 T1: owner-visible warning about dedup failure is now a safe
    // Chinese fallback (not raw "simulated dedup outage"). Full error
    // stays in stderr via safeOwnerError.
    expect(result.reply).toContain("去重检查失败")
    expect(result.reply).not.toContain("simulated dedup outage")
    // Trace marks the degraded path for §14 observability
    expect(result.traces.some((t) => t.startsWith("wechat-memory: dedup failed"))).toBe(true)
  })
})
