import { EventBridge } from "@butler/persistence/event-bridge.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import {
  openButlerDatabase,
  createRuntimeStore,
  createDurableMemoryStore,
  createDocumentStore,
  createProjectKnowledgeStore,
  createProcedureStore,
  createTaskStore,
  backfillRuntimeFromEventStore,
} from "@butler/persistence"
import { resetSharedLocalTracer } from "@butler/runtime/observability/local-tracer.js"
import { systemClock } from "@butler/ports/core/clock.js"
import type { ChannelKind, ChannelPort } from "@butler/ports/core/channel.js"
import { createWechatChannelPort } from "@butler/adapters"
import { makeWiring, type Wiring } from "./wiring.js"
import { bootstrapMcpTools, type McpToolBundle } from "./mcp-bootstrap.js"

function envTruthy(raw: string | undefined): boolean {
  if (!raw) return false
  const text = raw.trim().toLowerCase()
  return text === "1" || text === "true" || "yes" === text || "on" === text
}

/** Build the ChannelPort registry from env. Empty when no channel is enabled. */
function buildChannelPorts(env: NodeJS.ProcessEnv): ReadonlyMap<ChannelKind, ChannelPort> {
  const ports = new Map<ChannelKind, ChannelPort>()
  if (envTruthy(env["BUTLER_V5_ILINK_ENABLED"])) {
    const token = (env["WECHAT_TOKEN"] ?? "").trim()
    const baseUrl = (env["WECHAT_BASE_URL"] ?? env["ILINK_BASE_URL"] ?? "https://api.weixin.qq.com").trim()
    if (token) {
      ports.set("wechat", createWechatChannelPort({ baseUrl, token }))
    }
  }
  return ports
}

export interface ProductionWiringHandle {
  readonly wiring: Wiring
  readonly dbKind: string
  readonly mcp: McpToolBundle
  readonly close: () => Promise<void>
}

export type CreateProductionWiringResult =
  | { readonly ok: true; readonly value: ProductionWiringHandle }
  | { readonly ok: false; readonly reason: string }

/** Shared bootstrap for API server and CLI one-shot runs. */
export async function createProductionWiring(
  env: NodeJS.ProcessEnv = process.env,
): Promise<CreateProductionWiringResult> {
  const openedDb = await openButlerDatabase(env)
  if (!openedDb.ok) {
    return { ok: false, reason: openedDb.reason }
  }
  resetSharedLocalTracer(env)
  const db = openedDb.value.db
  const workerId = env["WORKER_ID"] ?? "w-default"
  const bridge = new EventBridge({ db, workerId })
  const runtimeStore = createRuntimeStore(db)
  const durableMemoryStore = createDurableMemoryStore(db)
  const documentStore = createDocumentStore(db)
  const projectKnowledgeStore = createProjectKnowledgeStore(db)
  const procedureStore = createProcedureStore(db)
  const taskStore = createTaskStore(db)
  // Composition Root: 注入系统时钟；测试可用 fixedClock 注入假时钟做确定性断言。
  const runEngine = new RunEngine(runtimeStore, undefined, systemClock)
  const mcp = await bootstrapMcpTools(env, { runtimeStore })
  const channels = buildChannelPorts(env)
  const wiring = makeWiring({
    bridge,
    workerId,
    runtimeStore,
    runEngine,
    db,
    mcp,
    durableMemoryStore,
    documentStore,
    projectKnowledgeStore,
    procedureStore,
    taskStore,
    channels,
    backfillConversation: async (conversationId) => {
      await backfillRuntimeFromEventStore(db, [conversationId])
    },
  })
  return {
    ok: true,
    value: {
      wiring,
      dbKind: openedDb.value.kind,
      mcp,
      close: async () => {
        await mcp.close?.()
        await openedDb.value.close()
      },
    },
  }
}
