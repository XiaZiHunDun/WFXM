import { EventBridge } from "@butler/persistence/event-bridge.js"
import { envTruthy } from "./env-util.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import {
  openButlerDatabase,
  createRuntimeStore,
  createDurableMemoryStore,
  createDocumentStore,
  createProjectKnowledgeStore,
  createProcedureStore,
  createTaskStore,
  createReminderStore,
  createTraceStore,
  backfillRuntimeFromEventStore,
} from "@butler/persistence"
import { parseTraceRetention } from "@butler/domain/observability/local-trace.js"
import { resetSharedLocalTracer } from "@butler/runtime/observability/local-tracer.js"
import { systemClock } from "@butler/ports/core/clock.js"
import type { ChannelKind, ChannelPort } from "@butler/ports/core/channel.js"
import { createWechatChannelPort } from "@butler/adapters"
import { makeWiring, type Wiring } from "./wiring.js"
import { bootstrapMcpTools, type McpToolBundle } from "./mcp-bootstrap.js"

/** Build the ChannelPort registry from env. Empty when no channel is enabled. */
function buildChannelPorts(env: NodeJS.ProcessEnv): ReadonlyMap<ChannelKind, ChannelPort> {
  const ports = new Map<ChannelKind, ChannelPort>()
  if (envTruthy(env["BUTLER_V5_ILINK_ENABLED"])) {
    const token = (env["WECHAT_TOKEN"] ?? "").trim()
    const baseUrl = (
      env["WECHAT_BASE_URL"] ??
      env["ILINK_BASE_URL"] ??
      "https://api.weixin.qq.com"
    ).trim()
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
  const db = openedDb.value.db
  const traceStore = createTraceStore(db)
  // Phase 5 P0: dual-write traces (memory ring buffer + batched DB sink).
  resetSharedLocalTracer(env, { sink: traceStore })
  const workerId = env["WORKER_ID"] ?? "w-default"
  const bridge = new EventBridge({ db, workerId })
  const runtimeStore = createRuntimeStore(db)
  const durableMemoryStore = createDurableMemoryStore(db)
  const documentStore = createDocumentStore(db)
  const projectKnowledgeStore = createProjectKnowledgeStore(db)
  const procedureStore = createProcedureStore(db)
  const taskStore = createTaskStore(db)
  const reminderStore = createReminderStore(db)
  // Startup retention prune; a failure only logs and never blocks boot.
  try {
    await traceStore.prune(parseTraceRetention(env))
  } catch (err) {
    // eslint-disable-next-line no-console -- operator log when no logger injected
    console.error("[butler-v5] trace retention prune failed on startup:", err)
  }
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
    reminderStore,
    traceStore,
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
