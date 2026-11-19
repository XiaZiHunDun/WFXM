/**
 * Shared harness for wechat command tests: one PGlite DB + full wiring with
 * the stores commands need, plus a temp active-project dir. Tests assert
 * command semantics (reply text + store state), never internal call order.
 *
 * Lives at tests/ root (tests/harness/ is not writable in this workspace).
 */
import { mkdtempSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { makeTestDb } from "@butler/persistence/testing.js"
import { EventBridge } from "@butler/persistence/event-bridge.js"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import {
  createDurableMemoryStore,
  createProjectKnowledgeStore,
  createTaskStore,
} from "@butler/persistence"
import { makeWiring, type Wiring } from "../apps/api/src/wiring.js"

export interface WechatCommandHarness {
  readonly db: Awaited<ReturnType<typeof makeTestDb>>
  readonly wiring: Wiring
  readonly env: NodeJS.ProcessEnv
  readonly storeDir: string
  close(): Promise<void>
}

export async function makeWechatCommandHarness(
  workerId = "wechat-cmd",
): Promise<WechatCommandHarness> {
  const db = await makeTestDb()
  const bridge = new EventBridge({ db: db.db, workerId })
  const runtimeStore = createRuntimeStore(db.db)
  const wiring = makeWiring({
    bridge,
    workerId,
    runtimeStore,
    runEngine: new RunEngine(runtimeStore),
    db: db.db,
    backfillConversation: async () => undefined,
    projectKnowledgeStore: createProjectKnowledgeStore(db.db),
    taskStore: createTaskStore(db.db),
    durableMemoryStore: createDurableMemoryStore(db.db),
  })
  const storeDir = mkdtempSync(join(tmpdir(), `butler-${workerId}-`))
  const subagentAudit = join(storeDir, "subagent.jsonl")
  const previousAuditPath = process.env["BUTLER_V5_SUBAGENT_AUDIT_PATH"]
  process.env["BUTLER_V5_SUBAGENT_AUDIT_PATH"] = subagentAudit

  const env: NodeJS.ProcessEnv = {
    BUTLER_V5_WECHAT_ACTIVE_PROJECT_STORE: join(storeDir, "active.json"),
    BUTLER_V5_PROJECT_KNOWLEDGE_INBOUND_MAP: "wechat:WFXM",
    BUTLER_V5_WECHAT_TOOL_ALLOWLIST_PATH: join(process.cwd(), "config/wechat-tool-allowlist.json"),
    BUTLER_V5_WECHAT_PROJECT_PATHS: join(process.cwd(), "config/wechat-project-paths.json"),
    BUTLER_V5_QUALITY_GATE_CONFIG: join(process.cwd(), "config/quality-gate.json"),
    BUTLER_V5_WORKSPACE_ROOT: join(process.cwd(), ".."),
    BUTLER_V5_MEMORY_DEDUP_ENABLED: "1",
    BUTLER_V5_SUBAGENT_ENABLED: "1",
    BUTLER_V5_SUBAGENT_AUDIT_PATH: subagentAudit,
  }

  return {
    db,
    wiring,
    env,
    storeDir,
    close: async () => {
      await db.close()
      rmSync(storeDir, { recursive: true, force: true })
      if (previousAuditPath === undefined) delete process.env["BUTLER_V5_SUBAGENT_AUDIT_PATH"]
      else process.env["BUTLER_V5_SUBAGENT_AUDIT_PATH"] = previousAuditPath
    },
  }
}
