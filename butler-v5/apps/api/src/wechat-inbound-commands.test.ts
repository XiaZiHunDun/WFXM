import { mkdtempSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { describe, expect, it, afterEach, beforeEach } from "vitest"
import { makeTestDb } from "@butler/persistence/testing.js"
import { EventBridge } from "@butler/persistence/event-bridge.js"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import { createDurableMemoryStore } from "@butler/persistence/durable-memory-store.js"
import { createTaskStore } from "@butler/persistence/task-procedure-store.js"
import { createDurableMemoryRecord } from "@butler/domain/knowledge/durable-memory.js"
import { setWechatActiveProjectId } from "./wechat-active-project.js"
import { makeWiring, type Wiring } from "./wiring.js"
import { tryWechatInboundCommand } from "./wechat-inbound-commands.js"
import { loadQualityGateConfig } from "./wechat-quality-gate.js"

describe("wechat inbound commands", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let wiring: Wiring
  let testEnv: NodeJS.ProcessEnv
  let storeDir = ""

  beforeEach(async () => {
    db = await makeTestDb()
    const bridge = new EventBridge({ db: db.db, workerId: "cmd-test" })
    wiring = makeWiring({
      bridge,
      workerId: "cmd-test",
      runtimeStore: createRuntimeStore(db.db),
      runEngine: new RunEngine(createRuntimeStore(db.db)),
      db: db.db,
      backfillConversation: async () => undefined,
      taskStore: createTaskStore(db.db),
      durableMemoryStore: createDurableMemoryStore(db.db),
    })
    storeDir = mkdtempSync(join(tmpdir(), "butler-cmd-"))
    testEnv = {
      BUTLER_V5_WECHAT_ACTIVE_PROJECT_STORE: join(storeDir, "active.json"),
      BUTLER_V5_PROJECT_KNOWLEDGE_INBOUND_MAP: "wechat:WFXM",
      BUTLER_V5_WECHAT_TOOL_ALLOWLIST_PATH: join(process.cwd(), "config/wechat-tool-allowlist.json"),
      BUTLER_V5_WECHAT_PROJECT_PATHS: join(process.cwd(), "config/wechat-project-paths.json"),
      BUTLER_V5_QUALITY_GATE_CONFIG: join(process.cwd(), "config/quality-gate.json"),
      BUTLER_V5_WORKSPACE_ROOT: join(process.cwd(), ".."),
    }
  })

  afterEach(async () => {
    await db.close()
    rmSync(storeDir, { recursive: true, force: true })
  })

  it("creates and lists project-scoped tasks", async () => {
    const add = await tryWechatInboundCommand({
      wiring,
      fromUserId: "u-task",
      content: "/待办 新增 修 smoke",
      env: testEnv,
    })
    expect(add?.reply).toContain("已添加待办")

    const list = await tryWechatInboundCommand({
      wiring,
      fromUserId: "u-task",
      content: "/待办",
      env: testEnv,
    })
    expect(list?.reply).toContain("修 smoke")
  })

  it("remembers and lists durable memory", async () => {
    const remember = await tryWechatInboundCommand({
      wiring,
      fromUserId: "u-mem",
      content: "/记住 第三卷主角名禁止修改",
      env: testEnv,
    })
    expect(remember?.reply).toContain("已记住")

    const list = await tryWechatInboundCommand({
      wiring,
      fromUserId: "u-mem",
      content: "/记忆",
      env: testEnv,
    })
    expect(list?.reply).toContain("第三卷")
  })

  it("/记忆候选 lists pending candidates scoped to active project", async () => {
    // seed 3 candidates: one in active project, one un-noted (always included), one in different project (excluded)
    setWechatActiveProjectId("owner-A", "WFXM", testEnv)
    const c1 = createDurableMemoryRecord({
      subject: "owner-A",
      content: "fact-in-active",
      sourceKind: "owner",
      status: "candidate",
      provenance: { note: "project:WFXM" },
    })
    const c2 = createDurableMemoryRecord({
      subject: "owner-A",
      content: "fact-un-noted",
      sourceKind: "owner",
      status: "candidate",
    })
    const c3 = createDurableMemoryRecord({
      subject: "owner-A",
      content: "fact-other-project",
      sourceKind: "owner",
      status: "candidate",
      provenance: { note: "project:OTHER" },
    })
    if (!c1.ok || !c2.ok || !c3.ok) throw new Error("seed")
    await wiring.durableMemoryStore!.create(c1.value)
    await wiring.durableMemoryStore!.create(c2.value)
    await wiring.durableMemoryStore!.create(c3.value)

    const result = await tryWechatInboundCommand({
      wiring,
      fromUserId: "owner-A",
      content: "/记忆候选",
      env: testEnv,
    })
    expect(result).not.toBeNull()
    expect(result!.reply).toContain("候选")
    expect(result!.reply).toContain("fact-in-active")
    // fact-un-noted should also be present (short-circuit inclusion)
    expect(result!.reply).toContain("fact-un-noted")
    // proves scope filter narrows
    expect(result!.reply).not.toContain("fact-other-project")
  })

  it("/记忆候选 returns empty message when no candidates", async () => {
    setWechatActiveProjectId("owner-no-candidates", "WFXM", testEnv)
    const result = await tryWechatInboundCommand({
      wiring,
      fromUserId: "owner-no-candidates",
      content: "/记忆候选",
      env: testEnv,
    })
    expect(result).not.toBeNull()
    expect(result!.reply).toContain("暂无 candidate 记忆")
  })

  it("loads quality gate config", () => {
    const cfg = loadQualityGateConfig({
      BUTLER_V5_QUALITY_GATE_CONFIG: join(process.cwd(), "config/quality-gate.json"),
    })
    expect(cfg?.projects?.["wechat"]?.commands.length).toBeGreaterThan(0)
  })

  it("runs /验 for wechat project", async () => {
    const gate = await tryWechatInboundCommand({
      wiring,
      fromUserId: "u-gate",
      content: "/验 surface-test",
      env: testEnv,
    })
    expect(gate?.reply).toContain("质量门禁")
    expect(gate?.reply).toMatch(/✓|✗/)
  }, 120_000)
})
