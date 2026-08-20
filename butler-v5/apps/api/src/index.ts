import { Hono } from "hono"
import { createRoutes } from "./routes.js"
import { createOwnerRoutes } from "./owner-routes.js"
import { makeWiring, type Wiring } from "./wiring.js"
import { EventBridge } from "@butler/runtime/bridge.js"
import { pickLLMProvider } from "@butler/adapters"
import {
  openButlerDatabase,
  createRuntimeStore,
  backfillRuntimeFromEventStore,
} from "@butler/persistence"
import { RunEngine } from "@butler/runtime/run-engine.js"
import { runSubagentWorker } from "./subagent-worker.js"
import { startWsServer } from "./ws-routes.js"

const app = new Hono()
const workerId = process.env["WORKER_ID"] ?? "w-default"

// Production (`NODE_ENV=production` + DATABASE_URL) uses Docker Postgres so
// conversation events survive gateway restart. Tests and local defaults stay
// in-process PGlite. `BUTLER_V5_DB` overrides. Postgres open failure exits
// rather than silently falling back to memory.
const openedDb = await openButlerDatabase(process.env)
if (!openedDb.ok) {
  // eslint-disable-next-line no-console -- operator log when no logger injected
  console.error(`[butler-v5] database open failed: ${openedDb.reason}`)
  process.exit(1)
}
// eslint-disable-next-line no-console -- operator log when no logger injected
console.error(`[butler-v5] event store: ${openedDb.value.kind}`)
const db = openedDb.value.db
const bridge = new EventBridge({ db, workerId })
const runtimeStore = createRuntimeStore(db)
const runEngine = new RunEngine(runtimeStore)
const wiring: Wiring = makeWiring({
  bridge,
  workerId,
  runtimeStore,
  runEngine,
  db,
  backfillConversation: async (conversationId) => {
    await backfillRuntimeFromEventStore(db, [conversationId])
  },
})
createRoutes(app, wiring)
createOwnerRoutes(app, wiring)

// R8.x.8: start the WebSocket push server so subagent replies (and
// any future event_store writes for a conversation) get delivered
// to connected clients in real-time. The Hono HTTP API stays on
// its own port — the WS server listens separately and shares the
// in-process subscriber registry. Port is `WS_PORT` env (default
// 3001; vitest uses an ephemeral port so e2e imports don't collide
// with docker wechat-mock on 3001). Host is `WS_HOST` (default
// 127.0.0.1 — loopback only).
const vitest = (process.env["VITEST"] ?? "").trim() !== ""
const wsPort = Number(process.env["WS_PORT"] ?? (vitest ? 0 : 3001))
const wsHost = process.env["WS_HOST"] ?? "127.0.0.1"
const wsHandle = await startWsServer({ port: wsPort, host: wsHost })

// R8.x.7: start the subagent worker so outbox `Delegate` messages
// written by `delegate_to_subagent` get consumed and the reply is
// appended to the parent conversation stream. The worker reads the
// same env as the request path (so DASHSCOPE/DEEPSEEK/ANTHROPIC_KEY
// are picked up uniformly) and is a no-op for non-`Delegate`
// aggregate types.
runSubagentWorker(bridge, pickLLMProvider, process.env)

// Clean up the WS server on shutdown so operator SIGINT/SIGTERM
// doesn't leave a half-open port behind.
const shutdown = (): void => {
  void wsHandle.close()
  void openedDb.value.close()
}
process.on("SIGINT", shutdown)
process.on("SIGTERM", shutdown)

// Named export exposes the live wiring for e2e real-path assertions
// (R8.2 uses wiring.eventBridge.loadStream to verify event_store writes).
export const __wiring__ = wiring
export const __wsHandle__ = wsHandle
export { startIlinkPollerIfEnabled } from "./ilink-poller.js"
export default app
