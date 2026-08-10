import { Layer } from "effect"
import type { PgliteDatabase } from "drizzle-orm/pglite"
import {
  loadSnapshot as persistenceLoadSnapshot,
  saveSnapshot as persistenceSaveSnapshot,
} from "@butler/persistence/snapshot.js"
import { SnapshotService } from "@butler/ports"
import { tryPromise } from "../port-helpers.js"

interface SnapshotAdapterConfig {
  readonly db: PgliteDatabase<Record<string, never>>
}

export function makePostgresSnapshotAdapter(config: SnapshotAdapterConfig) {
  return Layer.succeed(SnapshotService as never, {
    load: (streamId: string) =>
      tryPromise(
        () => persistenceLoadSnapshot(config.db, streamId),
        (err) =>
          new Error(`snapshot load failed: ${err instanceof Error ? err.message : String(err)}`),
      ),
    save: (streamId: string, version: number, payload: Record<string, unknown>) =>
      tryPromise(
        () => persistenceSaveSnapshot(config.db, streamId, version, payload),
        (err) =>
          new Error(`snapshot save failed: ${err instanceof Error ? err.message : String(err)}`),
      ),
  })
}
