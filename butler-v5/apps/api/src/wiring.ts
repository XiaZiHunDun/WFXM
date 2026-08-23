import type { EventBridge } from "@butler/runtime/bridge.js"
import type { RunEngine } from "@butler/runtime/run-engine.js"
import type { RuntimeStore } from "@butler/domain/runtime.js"
import type {
  ButlerDb,
  DurableMemoryStore,
  DocumentStore,
  ProcedureStore,
  TaskStore,
} from "@butler/persistence"
import type { McpToolBundle } from "./mcp-bootstrap.js"

export interface WiringConfig {
  readonly bridge: EventBridge
  readonly workerId: string
  readonly runtimeStore: RuntimeStore
  readonly runEngine: RunEngine
  readonly db: ButlerDb
  readonly backfillConversation: (conversationId: string) => Promise<void>
  readonly mcp?: McpToolBundle
  readonly durableMemoryStore?: DurableMemoryStore
  readonly documentStore?: DocumentStore
  readonly procedureStore?: ProcedureStore
  readonly taskStore?: TaskStore
}

export interface Wiring {
  readonly eventBridge: EventBridge
  readonly workerId: string
  readonly version: "v5"
  readonly runtimeStore: RuntimeStore
  readonly runEngine: RunEngine
  readonly db: ButlerDb
  readonly backfillConversation: (conversationId: string) => Promise<void>
  readonly mcp: McpToolBundle
  readonly durableMemoryStore: DurableMemoryStore | null
  readonly documentStore: DocumentStore | null
  readonly procedureStore: ProcedureStore | null
  readonly taskStore: TaskStore | null
}

/**
 * Build the v5 wiring: bridge + runtime services + version label.
 * The server (apps/api/src/index.ts) wires Hono with this object; routes
 * consume `eventBridge` for domain events.
 */
export function makeWiring(config: WiringConfig): Wiring {
  return {
    eventBridge: config.bridge,
    workerId: config.workerId,
    version: "v5",
    runtimeStore: config.runtimeStore,
    runEngine: config.runEngine,
    db: config.db,
    backfillConversation: config.backfillConversation,
    mcp: config.mcp ?? {
      runtimeTools: [],
      llmTools: [],
      mode: "off",
      discovered: [],
      servers: [],
      serverIdByCapability: {},
    },
    durableMemoryStore: config.durableMemoryStore ?? null,
    documentStore: config.documentStore ?? null,
    procedureStore: config.procedureStore ?? null,
    taskStore: config.taskStore ?? null,
  }
}
