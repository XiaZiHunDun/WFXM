import type { EventBridge } from "@butler/runtime/bridge.js"
import type { RunEngine } from "@butler/runtime/run-engine.js"
import type { RuntimeStore } from "@butler/domain/runtime.js"
import type { ButlerDb } from "@butler/persistence"
import type { makePostgresAdapters } from "@butler/adapters/postgres/index.js"

export type PostgresAdapters = ReturnType<typeof makePostgresAdapters>

export interface WiringConfig {
  readonly bridge: EventBridge
  readonly adapters: PostgresAdapters
  readonly workerId: string
  readonly runtimeStore: RuntimeStore
  readonly runEngine: RunEngine
  readonly db: ButlerDb
  readonly backfillConversation: (conversationId: string) => Promise<void>
}

export interface Wiring {
  readonly eventBridge: EventBridge
  readonly adapters: PostgresAdapters
  readonly workerId: string
  readonly version: "v5"
  readonly runtimeStore: RuntimeStore
  readonly runEngine: RunEngine
  readonly db: ButlerDb
  readonly backfillConversation: (conversationId: string) => Promise<void>
}

/**
 * Build the v5 wiring: bridge + adapters + version label.
 * The server (apps/api/src/index.ts) wires Hono with this object; routes
 * consume `eventBridge` for domain events.
 */
export function makeWiring(config: WiringConfig): Wiring {
  return {
    eventBridge: config.bridge,
    adapters: config.adapters,
    workerId: config.workerId,
    version: "v5",
    runtimeStore: config.runtimeStore,
    runEngine: config.runEngine,
    db: config.db,
    backfillConversation: config.backfillConversation,
  }
}
