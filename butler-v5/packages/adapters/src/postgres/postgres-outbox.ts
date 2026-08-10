import { Layer } from "effect"
import type { PgliteDatabase } from "drizzle-orm/pglite"
import {
  enqueueOutbox as persistenceEnqueueOutbox,
  claimOutbox as persistenceClaimOutbox,
  completeOutbox as persistenceCompleteOutbox,
  failOutbox as persistenceFailOutbox,
} from "@butler/persistence/outbox.js"
import { runWorkerOnce as persistenceRunWorkerOnce } from "@butler/persistence/worker.js"
import { OutboxService } from "@butler/ports"
import { tryPromise } from "../port-helpers.js"

interface OutboxAdapterConfig {
  readonly db: PgliteDatabase<Record<string, never>>
  readonly workerId: string
  readonly leaseMs?: number
}

const DEFAULT_LEASE_MS = 60_000

export function makePostgresOutboxAdapter(config: OutboxAdapterConfig) {
  return Layer.succeed(OutboxService as never, {
    enqueue: (input: {
      streamId: string
      aggregateType: string
      payload: Record<string, unknown>
    }) =>
      tryPromise(
        () => persistenceEnqueueOutbox(config.db, input),
        (err) =>
          new Error(`outbox enqueue failed: ${err instanceof Error ? err.message : String(err)}`),
      ),
    claim: () =>
      tryPromise(
        () =>
          persistenceClaimOutbox(config.db, config.workerId, config.leaseMs ?? DEFAULT_LEASE_MS),
        (err) =>
          new Error(`outbox claim failed: ${err instanceof Error ? err.message : String(err)}`),
      ),
    complete: (id: string) =>
      tryPromise(
        () => persistenceCompleteOutbox(config.db, id),
        (err) =>
          new Error(`outbox complete failed: ${err instanceof Error ? err.message : String(err)}`),
      ),
    fail: (id: string, err: string) =>
      tryPromise(
        () => persistenceFailOutbox(config.db, id, err),
        (err2) =>
          new Error(`outbox fail failed: ${err2 instanceof Error ? err2.message : String(err2)}`),
      ),
    runWorker: (handler: Parameters<typeof persistenceRunWorkerOnce>[3]) =>
      tryPromise(
        () =>
          persistenceRunWorkerOnce(
            config.db,
            config.workerId,
            config.leaseMs ?? DEFAULT_LEASE_MS,
            handler,
          ),
        (err) =>
          new Error(`outbox runWorker failed: ${err instanceof Error ? err.message : String(err)}`),
      ),
  })
}
