import { Layer } from "effect"
import type { PgliteDatabase } from "drizzle-orm/pglite"
import {
  loadSnapshot as persistenceLoadSnapshot,
  saveSnapshot as persistenceSaveSnapshot,
} from "@butler/persistence/snapshot.js"
import { SnapshotService } from "./tags.js"

interface SnapshotAdapterConfig {
  readonly db: PgliteDatabase<Record<string, never>>
}

export function makePostgresSnapshotAdapter(config: SnapshotAdapterConfig) {
  return Layer.succeed(SnapshotService, {
    load: (streamId: string) => persistenceLoadSnapshot(config.db, streamId),
    save: (streamId: string, version: number, payload: Record<string, unknown>) =>
      persistenceSaveSnapshot(config.db, streamId, version, payload),
  })
}
