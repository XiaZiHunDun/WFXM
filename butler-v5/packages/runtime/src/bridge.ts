/**
 * EventBridge wraps the R3 persistence public API for AgentKernel use.
 * Runtime has no direct knowledge of pglite/postgres; it interacts only
 * via this bridge.
 */
import type { ButlerDb } from "@butler/persistence"
import {
  appendEvents,
  loadStream,
  nextVersion,
  subscribeStream,
  type ActorRef,
  type EventStoreRow,
} from "@butler/persistence/event-store.js"
import { enqueueOutbox } from "@butler/persistence/outbox.js"
import {
  applyProjection,
  registerProjection,
  rebuildProjection,
} from "@butler/persistence/projections.js"
import { loadSnapshot, saveSnapshot } from "@butler/persistence/snapshot.js"
import { runWorkerOnce } from "@butler/persistence/worker.js"

export interface EventBridgeConfig {
  readonly db: ButlerDb
  readonly workerId: string
  readonly leaseMs?: number
}

export class EventBridge {
  constructor(private readonly config: EventBridgeConfig) {}

  async appendConversationEvent(input: {
    streamId: string
    event: unknown
    eventId: string
    eventType: string
    correlationId: string
    actor: ActorRef
  }) {
    return appendEvents(this.config.db, input.streamId, input.event, {
      eventId: input.eventId,
      eventType: input.eventType,
      eventVersion: await nextVersion(this.config.db, input.streamId),
      correlationId: input.correlationId,
      occurredAt: new Date(),
      actor: input.actor,
    })
  }

  loadStream(streamId: string) {
    return loadStream(this.config.db, streamId)
  }

  subscribe(streamId: string, handler: (e: EventStoreRow) => void) {
    return subscribeStream(this.config.db, streamId, handler)
  }

  enqueueOutbox(input: {
    streamId: string
    aggregateType: string
    payload: Record<string, unknown>
  }) {
    return enqueueOutbox(this.config.db, input)
  }

  runWorker(handler: Parameters<typeof runWorkerOnce>[3]) {
    return runWorkerOnce(
      this.config.db,
      this.config.workerId,
      this.config.leaseMs ?? 60_000,
      handler,
    )
  }

  applyProjection(streamId: string, name: string) {
    return applyProjection(this.config.db, streamId, name)
  }

  rebuildProjection(streamId: string, name: string) {
    return rebuildProjection(this.config.db, streamId, name)
  }

  registerProjection(name: string, handler: Parameters<typeof registerProjection>[1]) {
    return registerProjection(name, handler)
  }

  saveSnapshot(streamId: string, version: number, payload: Record<string, unknown>) {
    return saveSnapshot(this.config.db, streamId, version, payload)
  }

  loadSnapshot(streamId: string) {
    return loadSnapshot(this.config.db, streamId)
  }
}
