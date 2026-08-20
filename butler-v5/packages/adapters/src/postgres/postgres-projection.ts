import { Layer } from "effect"
import type { ButlerDb } from "@butler/persistence"
import {
  applyProjection as persistenceApplyProjection,
  rebuildProjection as persistenceRebuildProjection,
  registerProjection as persistenceRegisterProjection,
  type Handler as ProjectionHandler,
} from "@butler/persistence/projections.js"
import { ProjectionService } from "@butler/ports"
import { tryPromise } from "../port-helpers.js"

interface ProjectionAdapterConfig {
  readonly db: ButlerDb
}

export function makePostgresProjectionAdapter(config: ProjectionAdapterConfig) {
  return Layer.succeed(ProjectionService as never, {
    apply: (streamId: string, name: string) =>
      tryPromise(
        () => persistenceApplyProjection(config.db, streamId, name),
        (err) =>
          new Error(`projection apply failed: ${err instanceof Error ? err.message : String(err)}`),
      ),
    rebuild: (streamId: string, name: string) =>
      tryPromise(
        () => persistenceRebuildProjection(config.db, streamId, name),
        (err) =>
          new Error(
            `projection rebuild failed: ${err instanceof Error ? err.message : String(err)}`,
          ),
      ),
    register: (name: string, handler: ProjectionHandler) =>
      tryPromise(
        async () => persistenceRegisterProjection(name, handler),
        (err) =>
          new Error(
            `projection register failed: ${err instanceof Error ? err.message : String(err)}`,
          ),
      ),
  })
}
