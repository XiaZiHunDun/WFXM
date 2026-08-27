import { mkdtempSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { describe, expect, it, afterEach, beforeEach } from "vitest"
import { makeTestDb } from "@butler/persistence/testing.js"
import { EventBridge } from "@butler/persistence/event-bridge.js"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import { createProjectKnowledgeStore } from "@butler/persistence/project-knowledge-store.js"
import { createTaskStore } from "@butler/persistence/task-procedure-store.js"
import { makeWiring, type Wiring } from "./wiring.js"
import {
  loadWechatProjectPathsConfig,
  summarizeWechatToolProfile,
  tryWechatProjectCommand,
} from "./wechat-project-surface.js"
import { normalizeWechatSwitchCommand } from "./wechat-project-switch.js"
import { loadWechatToolAllowlistFromPath } from "./wechat-tool-allowlist.js"

describe("wechat project surface", () => {
  let storeDir = ""

  afterEach(() => {
    if (storeDir) rmSync(storeDir, { recursive: true, force: true })
  })

  function env(extra: Record<string, string> = {}): NodeJS.ProcessEnv {
    storeDir = mkdtempSync(join(tmpdir(), "butler-surface-"))
    return {
      BUTLER_V5_WECHAT_ACTIVE_PROJECT_STORE: join(storeDir, "active.json"),
      BUTLER_V5_PROJECT_KNOWLEDGE_INBOUND_MAP: "wechat:WFXM,LingWen1:LingWen,灵文1号:LingWen",
      BUTLER_V5_WECHAT_TOOL_ALLOWLIST_PATH: "config/wechat-tool-allowlist.json",
      BUTLER_V5_WECHAT_PROJECT_PATHS: join(process.cwd(), "config/wechat-project-paths.json"),
      BUTLER_V5_WORKSPACE_ROOT: join(process.cwd(), ".."),
      ...extra,
    }
  }

  it("loads project paths config", () => {
    const cfg = loadWechatProjectPathsConfig({
      BUTLER_V5_WECHAT_PROJECT_PATHS: join(process.cwd(), "config/wechat-project-paths.json"),
    })
    expect(cfg?.projects?.["LingWen1"]?.readmePath).toContain("LingWen1")
  })

  it("summarizes per-project MCP profiles", () => {
    const e = env()
    const allowlistPath = join(process.cwd(), "config/wechat-tool-allowlist.json")
    expect(loadWechatToolAllowlistFromPath(allowlistPath)?.projects?.["灵文1号"]?.mcpTools).toHaveLength(2)
    const lingwen = summarizeWechatToolProfile({
      projectId: "灵文1号",
      env: { ...e, BUTLER_V5_WECHAT_TOOL_ALLOWLIST_PATH: allowlistPath },
      mcpBundle: {
        mode: "multi",
        runtimeTools: [
          { name: "mcp_markitdown_convert_to_markdown" as never, risk: "low", run: async () => ({ ok: true, output: "" }) },
          { name: "mcp_firecrawl_firecrawl_scrape" as never, risk: "low", run: async () => ({ ok: true, output: "" }) },
          { name: "mcp_github_search_code" as never, risk: "low", run: async () => ({ ok: true, output: "" }) },
        ],
        llmTools: [],
        discovered: [],
        servers: [],
        serverIdByCapability: {},
      },
    })
    expect(lingwen.mcp).toBe(2)
    expect(lingwen.total).toBeGreaterThan(lingwen.mcp)
  })

  it("normalizes natural-language switch phrasing", () => {
    expect(normalizeWechatSwitchCommand("切换到 灵文1号")).toBe("/切换 灵文1号")
  })
})

describe("tryWechatProjectCommand integration", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let wiring: Wiring
  let testEnv: NodeJS.ProcessEnv
  let storeDir = ""

  beforeEach(async () => {
    db = await makeTestDb()
    const bridge = new EventBridge({ db: db.db, workerId: "surface-test" })
    wiring = makeWiring({
      bridge,
      workerId: "surface-test",
      runtimeStore: createRuntimeStore(db.db),
      runEngine: new RunEngine(createRuntimeStore(db.db)),
      db: db.db,
      backfillConversation: async () => undefined,
      projectKnowledgeStore: createProjectKnowledgeStore(db.db),
      taskStore: createTaskStore(db.db),
    })
    storeDir = mkdtempSync(join(tmpdir(), "butler-surface-int-"))
    testEnv = {
      BUTLER_V5_WECHAT_ACTIVE_PROJECT_STORE: join(storeDir, "active.json"),
      BUTLER_V5_PROJECT_KNOWLEDGE_INBOUND_MAP: "wechat:WFXM,LingWen1:LingWen",
      BUTLER_V5_WECHAT_TOOL_ALLOWLIST_PATH: join(process.cwd(), "config/wechat-tool-allowlist.json"),
      BUTLER_V5_WECHAT_PROJECT_PATHS: join(process.cwd(), "config/wechat-project-paths.json"),
      BUTLER_V5_WORKSPACE_ROOT: join(process.cwd(), ".."),
    }
  })

  afterEach(async () => {
    await db.close()
    rmSync(storeDir, { recursive: true, force: true })
  })

  it("returns enriched /项目 and /项目概况", async () => {
    const list = await tryWechatProjectCommand({
      wiring,
      fromUserId: "u-surface",
      content: "/项目",
      env: testEnv,
    })
    expect(list?.reply).toContain("项目列表")
    expect(list?.reply).toContain("wechat")

    await tryWechatProjectCommand({
      wiring,
      fromUserId: "u-surface",
      content: "/切换 LingWen1",
      env: testEnv,
    })
    const overview = await tryWechatProjectCommand({
      wiring,
      fromUserId: "u-surface",
      content: "/项目概况",
      env: testEnv,
    })
    expect(overview?.reply).toContain("灵文")
    expect(overview?.reply).toContain("工具")
  })

  it("returns /项目 体检 for active project", async () => {
    const health = await tryWechatProjectCommand({
      wiring,
      fromUserId: "u-surface",
      content: "/项目 体检",
      env: testEnv,
    })
    expect(health?.reply).toContain("体检")
    expect(health?.reply).toMatch(/✓|✗/)
  })
})
