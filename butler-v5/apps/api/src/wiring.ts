import type { EventBridge } from "@butler/runtime/bridge.js"
import type { makePostgresAdapters } from "@butler/adapters/postgres/index.js"

export type PostgresAdapters = ReturnType<typeof makePostgresAdapters>

export interface WiringConfig {
  readonly bridge: EventBridge
  readonly adapters: PostgresAdapters
  readonly workerId: string
}

export interface Wiring {
  readonly eventBridge: EventBridge
  readonly adapters: PostgresAdapters
  readonly workerId: string
  readonly version: "v5"
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
  }
}
