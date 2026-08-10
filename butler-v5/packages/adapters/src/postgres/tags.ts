// packages/adapters/src/postgres/tags.ts
// Local Context.Tag definitions for OutboxService, SnapshotService,
// ProjectionService. These mirror the shape of the corresponding
// persistence public API so the postgres adapters can satisfy them
// without mutating @butler/ports (which is in the protected file list).

import { Context } from "effect"
import type { EventStoreRow } from "@butler/persistence/event-store.js"

export class OutboxService extends Context.Tag("OutboxService")<
  OutboxService,
  {
    readonly enqueue: (input: {
      readonly streamId: string
      readonly aggregateType: string
      readonly payload: Record<string, unknown>
    }) => Promise<string>
    readonly claim: () => Promise<readonly unknown[]>
    readonly complete: (id: string) => Promise<void>
    readonly fail: (id: string, err: string) => Promise<void>
    readonly runWorker: (handler: (msg: unknown) => Promise<void>) => Promise<number>
  }
>() {}

export class SnapshotService extends Context.Tag("SnapshotService")<
  SnapshotService,
  {
    readonly load: (streamId: string) => Promise<unknown>
    readonly save: (
      streamId: string,
      version: number,
      payload: Record<string, unknown>,
    ) => Promise<void>
  }
>() {}

export class ProjectionService extends Context.Tag("ProjectionService")<
  ProjectionService,
  {
    readonly apply: (streamId: string, name: string) => Promise<void>
    readonly rebuild: (streamId: string, name: string) => Promise<void>
    readonly register: (name: string, handler: (e: EventStoreRow) => Promise<void>) => void
  }
>() {}
