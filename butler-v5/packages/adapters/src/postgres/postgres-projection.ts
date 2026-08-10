import { Layer } from "effect"
import type { PgliteDatabase } from "drizzle-orm/pglite"
import {
  applyProjection as persistenceApplyProjection,
  rebuildProjection as persistenceRebuildProjection,
  registerProjection as persistenceRegisterProjection,
  type Handler as ProjectionHandler,
} from "@butler/persistence/projections.js"
import { ProjectionService } from "./tags.js"

interface ProjectionAdapterConfig {
  readonly db: PgliteDatabase<Record<string, never>>
}

export function makePostgresProjectionAdapter(config: ProjectionAdapterConfig) {
  return Layer.succeed(ProjectionService, {
    apply: (streamId: string, name: string) =>
      persistenceApplyProjection(config.db, streamId, name),
    rebuild: (streamId: string, name: string) =>
      persistenceRebuildProjection(config.db, streamId, name),
    register: (name: string, handler: ProjectionHandler) =>
      persistenceRegisterProjection(name, handler),
  })
}
