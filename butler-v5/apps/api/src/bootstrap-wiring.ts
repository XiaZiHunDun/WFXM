import { EventBridge } from "@butler/runtime/bridge.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import {
  openButlerDatabase,
  createRuntimeStore,
  createDurableMemoryStore,
  createDocumentStore,
  createProcedureStore,
  createTaskStore,
  backfillRuntimeFromEventStore,
} from "@butler/persistence"
import { resetSharedLocalTracer } from "@butler/runtime/observability/local-tracer.js"
import { makeWiring, type Wiring } from "./wiring.js"
import { bootstrapMcpTools, type McpToolBundle } from "./mcp-bootstrap.js"

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
  const procedureStore = createProcedureStore(db)
  const taskStore = createTaskStore(db)
  const runEngine = new RunEngine(runtimeStore)
  const mcp = await bootstrapMcpTools(env)
  const wiring = makeWiring({
    bridge,
    workerId,
    runtimeStore,
    runEngine,
    db,
    mcp,
    durableMemoryStore,
    documentStore,
    procedureStore,
    taskStore,
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
