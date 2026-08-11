import { Hono } from "hono"
import { PGlite } from "@electric-sql/pglite"
import { drizzle } from "drizzle-orm/pglite"
import { createRoutes } from "./routes.js"
import { makeWiring } from "./wiring.js"
import { EventBridge } from "@butler/runtime/bridge.js"
import { makePostgresAdapters } from "@butler/adapters/postgres/index.js"

const app = new Hono()
const workerId = process.env["WORKER_ID"] ?? "w-default"

// R7.0 stub: pglite-backed in-process Drizzle. Production wiring lands
// in R7.2 with a real DATABASE_URL.
const pg = new PGlite()
const db = drizzle(pg, {})
const bridge = new EventBridge({ db, workerId })
const adapters = makePostgresAdapters({ db, workerId })
const wiring = makeWiring({ bridge, adapters, workerId })
createRoutes(app, wiring)

export default app
