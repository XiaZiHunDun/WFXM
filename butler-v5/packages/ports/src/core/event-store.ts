import type { ActorRef } from "@butler/domain/event-sourcing.js"

/**
 * EventStore Port — Core 依赖的事件存储抽象。
 *
 * Application 内核（agent-kernel / delegate-runtime）只依赖该接口，
 * 不 import 具体 persistence。实现由 driven adapter 提供：
 * `packages/persistence/src/event-bridge.ts` 中的 EventBridge implements
 * 本端口，Composition Root 注入。仅依赖 domain 类型（DESIGN §7 / §17）。
 */
export interface EventStorePort {
  readonly appendConversationEvent: (input: {
    readonly streamId: string
    readonly event: unknown
    readonly eventId: string
    readonly eventType: string
    readonly correlationId: string
    readonly actor: ActorRef
  }) => Promise<unknown>

  readonly appendConversationEventWithOutbox: (input: {
    readonly streamId: string
    readonly event: unknown
    readonly eventId: string
    readonly eventType: string
    readonly correlationId: string
    readonly actor: ActorRef
    readonly outbox: {
      readonly aggregateType: string
      readonly payload: Record<string, unknown>
    }
  }) => Promise<string>
}