import { Hono } from "hono"
import { PGlite } from "@electric-sql/pglite"
import { drizzle } from "drizzle-orm/pglite"
import { readFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { createRoutes } from "./routes.js"
import { makeWiring, type Wiring } from "./wiring.js"
import { EventBridge } from "@butler/runtime/bridge.js"
import { makePostgresAdapters } from "@butler/adapters/postgres/index.js"
import { pickLLMProvider } from "@butler/adapters"
import { runSubagentWorker } from "./subagent-worker.js"

const app = new Hono()
const workerId = process.env["WORKER_ID"] ?? "w-default"

// In-process pglite with idempotent schema bootstrap. Production wiring
// swaps this for a real DATABASE_URL via Postgres adapters (R7.0).
const pg = new PGlite()
const migrationsPath = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../../packages/persistence/src/migrations/0001_initial.sql",
)
await pg.exec(readFileSync(migrationsPath, "utf8"))

const db = drizzle(pg, {})
const bridge = new EventBridge({ db, workerId })
const adapters = makePostgresAdapters({ db, workerId })
const wiring: Wiring = makeWiring({ bridge, adapters, workerId })
createRoutes(app, wiring)

// R8.x.7: start the subagent worker so outbox `Delegate` messages
// written by `delegate_to_subagent` get consumed and the reply is
// appended to the parent conversation stream. The worker reads the
// same env as the request path (so DASHSCOPE/DEEPSEEK/ANTHROPIC_KEY
// are picked up uniformly) and is a no-op for non-`Delegate`
// aggregate types.
runSubagentWorker(bridge, pickLLMProvider, process.env)

// Named export exposes the live wiring for e2e real-path assertions
// (R8.2 uses wiring.eventBridge.loadStream to verify event_store writes).
export const __wiring__ = wiring
export default app
