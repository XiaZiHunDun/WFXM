import type { EventBridge } from "@butler/runtime/bridge.js"
import type { RunEngine } from "@butler/runtime/run-engine.js"
import type { RuntimeStore } from "@butler/domain/runtime.js"
import type { ButlerDb } from "@butler/persistence"
import type { McpToolBundle } from "./mcp-bootstrap.js"

export interface WiringConfig {
  readonly bridge: EventBridge
  readonly workerId: string
  readonly runtimeStore: RuntimeStore
  readonly runEngine: RunEngine
  readonly db: ButlerDb
  readonly backfillConversation: (conversationId: string) => Promise<void>
  readonly mcp?: McpToolBundle
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
    },
  }
}
