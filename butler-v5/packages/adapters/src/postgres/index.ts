import { Layer } from "effect"
import type { ButlerDb } from "@butler/persistence"
import { makePostgresEventStoreAdapter } from "./postgres-event-store.js"
import { makePostgresOutboxAdapter } from "./postgres-outbox.js"
import { makePostgresSnapshotAdapter } from "./postgres-snapshot.js"
import { makePostgresProjectionAdapter } from "./postgres-projection.js"
import { EventBridge } from "@butler/runtime"

interface PostgresAdapterInput {
  readonly db: ButlerDb
  readonly workerId?: string
  readonly leaseMs?: number
}

export function makePostgresAdapters(input: PostgresAdapterInput) {
  const eventStore = makePostgresEventStoreAdapter({ db: input.db })
  const outbox = makePostgresOutboxAdapter({
    db: input.db,
    workerId: input.workerId ?? "w-default",
    ...(input.leaseMs !== undefined ? { leaseMs: input.leaseMs } : {}),
  })
  const snapshot = makePostgresSnapshotAdapter({ db: input.db })
  const projection = makePostgresProjectionAdapter({ db: input.db })
  const eventBridge = new EventBridge({ db: input.db, workerId: input.workerId ?? "w-default" })
  return {
    eventStore,
    outbox,
    snapshot,
    projection,
    eventBridge,
    layer: Layer.mergeAll(eventStore, outbox, snapshot, projection) as Layer.Layer<
      unknown,
      never,
      never
    >,
  }
}
