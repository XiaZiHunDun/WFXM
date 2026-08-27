/**
 * EventBridge — persistence 侧的 driven adapter，实现 Core 的
 * `@butler/ports` EventStorePort 及其它事件存储操作。
 *
 * 自 R-hex 起由 `packages/runtime/src/bridge.ts` 迁移至此：Core 只依赖
 * 抽象端口（`packages/ports/src/core/event-store.ts`），不再 import 具体
 * persistence。Composition Root（apps/api）构造本类并注入到
 * agent-kernel / delegate-runtime / tools。
 */
import type { ButlerDb } from "./db.js"
import {
  appendEventAndEnqueueOutbox,
  appendEventsWithRetry,
  loadStream,
  subscribeStream,
  type ActorRef,
  type EventStoreRow,
} from "./event-store.js"
import { enqueueOutbox } from "./outbox.js"
import {
  applyProjection,
  registerProjection,
  rebuildProjection,
} from "./projections.js"
import { loadSnapshot, saveSnapshot } from "./snapshot.js"
import { runWorkerOnce } from "./worker.js"
import type { EventStorePort } from "@butler/ports/core/event-store.js"

export interface EventBridgeConfig {
  readonly db: ButlerDb
  readonly workerId: string
  readonly leaseMs?: number
}

export class EventBridge implements EventStorePort {
  constructor(private readonly config: EventBridgeConfig) {}

  async appendConversationEvent(input: {
    streamId: string
    event: unknown
    eventId: string
    eventType: string
    correlationId: string
    actor: ActorRef
  }) {
    return appendEventsWithRetry(this.config.db, input.streamId, input.event, {
      eventId: input.eventId,
      eventType: input.eventType,
      correlationId: input.correlationId,
      occurredAt: new Date(),
      actor: input.actor,
    })
  }

  async appendConversationEventWithOutbox(input: {
    streamId: string
    event: unknown
    eventId: string
    eventType: string
    correlationId: string
    actor: ActorRef
    outbox: {
      aggregateType: string
      payload: Record<string, unknown>
    }
  }): Promise<string> {
    return appendEventAndEnqueueOutbox(
      this.config.db,
      input.streamId,
      input.event,
      {
        eventId: input.eventId,
        eventType: input.eventType,
        correlationId: input.correlationId,
        occurredAt: new Date(),
        actor: input.actor,
      },
      {
        streamId: input.streamId,
        aggregateType: input.outbox.aggregateType,
        payload: input.outbox.payload,
      },
    )
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