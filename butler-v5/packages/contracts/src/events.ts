import type { EventEnvelope, StreamType } from "../../domain/src/event-sourcing.js"

export type ContractEvent = EventEnvelope & { readonly streamType: StreamType }

export interface EventSubscribeRequest {
  readonly streamTypes: readonly StreamType[]
  readonly fromVersion: number
}

export interface EventBatchResponse {
  readonly events: readonly ContractEvent[]
  readonly nextVersion: number
}
