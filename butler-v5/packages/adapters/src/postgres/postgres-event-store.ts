import { Layer } from "effect"
import type { ButlerDb } from "@butler/persistence"
import {
  appendEvents as persistenceAppendEvents,
  loadStream as persistenceLoadStream,
  nextVersion as persistenceNextVersion,
  subscribeStream as persistenceSubscribeStream,
  type EventStoreRow,
  type ActorRef,
} from "@butler/persistence/event-store.js"
import { EventStoreService } from "@butler/ports"

interface PostgresAdapterConfig {
  readonly db: ButlerDb
}

export function makePostgresEventStoreAdapter(config: PostgresAdapterConfig) {
  // The persistence EventBridge surface (appendConversationEvent / loadStream /
  // subscribe / nextVersion) is intentionally narrower than the R2 EventStoreService
  // contract (append / load / subscribe as Effect/Stream). The cast lets the
  // adapter ship as a skeleton while a follow-up R5.x scope reconciles shapes.
  return Layer.succeed(EventStoreService, {
    appendConversationEvent: (input: {
      streamId: string
      event: unknown
      eventId: string
      eventType: string
      correlationId: string
      actor: ActorRef
    }) => {
      const version = 0
      return persistenceAppendEvents(config.db, input.streamId, input.event, {
        eventId: input.eventId,
        eventType: input.eventType,
        eventVersion: version || 1,
        correlationId: input.correlationId,
        occurredAt: new Date(),
        actor: input.actor,
      })
    },
    loadStream: (streamId: string) => persistenceLoadStream(config.db, streamId),
    subscribe: (streamId: string, handler: (e: EventStoreRow) => void) =>
      persistenceSubscribeStream(config.db, streamId, handler),
    nextVersion: (streamId: string) => persistenceNextVersion(config.db, streamId),
  } as never)
}
