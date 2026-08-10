import { Layer } from "effect"
import type { PgliteDatabase } from "drizzle-orm/pglite"
import {
  enqueueOutbox as persistenceEnqueueOutbox,
  claimOutbox as persistenceClaimOutbox,
  completeOutbox as persistenceCompleteOutbox,
  failOutbox as persistenceFailOutbox,
} from "@butler/persistence/outbox.js"
import { runWorkerOnce as persistenceRunWorkerOnce } from "@butler/persistence/worker.js"
import { OutboxService } from "./tags.js"

interface OutboxAdapterConfig {
  readonly db: PgliteDatabase<Record<string, never>>
  readonly workerId: string
  readonly leaseMs?: number
}

const DEFAULT_LEASE_MS = 60_000

export function makePostgresOutboxAdapter(config: OutboxAdapterConfig) {
  return Layer.succeed(OutboxService, {
    enqueue: (input: {
      streamId: string
      aggregateType: string
      payload: Record<string, unknown>
    }) => persistenceEnqueueOutbox(config.db, input),
    claim: () =>
      persistenceClaimOutbox(config.db, config.workerId, config.leaseMs ?? DEFAULT_LEASE_MS),
    complete: (id: string) => persistenceCompleteOutbox(config.db, id),
    fail: (id: string, err: string) => persistenceFailOutbox(config.db, id, err),
    runWorker: (handler: Parameters<typeof persistenceRunWorkerOnce>[3]) =>
      persistenceRunWorkerOnce(
        config.db,
        config.workerId,
        config.leaseMs ?? DEFAULT_LEASE_MS,
        handler,
      ),
  })
}
