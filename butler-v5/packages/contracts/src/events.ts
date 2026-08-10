import type { EventEnvelope, StreamType } from "@butler/domain"

export type ContractEvent = EventEnvelope & { readonly streamType: StreamType }

export interface EventSubscribeRequest {
  readonly streamTypes: readonly StreamType[]
  readonly fromVersion: number
}

export interface EventBatchResponse {
  readonly events: readonly ContractEvent[]
  readonly nextVersion: number
}
