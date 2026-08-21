import { Hono } from "hono"
import { createRoutes } from "./routes.js"
import { createOwnerRoutes } from "./owner-routes.js"
import { createProductionWiring } from "./bootstrap-wiring.js"
import { pickLLMProvider } from "@butler/adapters"
import { runSubagentWorker } from "./subagent-worker.js"
import { startWsServer } from "./ws-routes.js"

const app = new Hono()

const boot = await createProductionWiring(process.env)
if (!boot.ok) {
  // eslint-disable-next-line no-console -- operator log when no logger injected
  console.error(`[butler-v5] database open failed: ${boot.reason}`)
  process.exit(1)
}
// eslint-disable-next-line no-console -- operator log when no logger injected
console.error(`[butler-v5] event store: ${boot.value.dbKind}`)
const wiring = boot.value.wiring
if (boot.value.mcp.mode !== "off") {
  // eslint-disable-next-line no-console -- operator log when no logger injected
  console.error(
    `[butler-v5] MCP enabled mode=${boot.value.mcp.mode} tools=${boot.value.mcp.runtimeTools.length}`,
  )
}
createRoutes(app, wiring)
createOwnerRoutes(app, wiring)

const vitest = (process.env["VITEST"] ?? "").trim() !== ""
const wsPort = Number(process.env["WS_PORT"] ?? (vitest ? 0 : 3001))
const wsHost = process.env["WS_HOST"] ?? "127.0.0.1"
const wsHandle = await startWsServer({ port: wsPort, host: wsHost })

runSubagentWorker(wiring.eventBridge, pickLLMProvider, process.env, {
  runtimeStore: wiring.runtimeStore,
})

const shutdown = (): void => {
  void wsHandle.close()
  void boot.value.close()
}
process.on("SIGINT", shutdown)
process.on("SIGTERM", shutdown)

export const __wiring__ = wiring
export const __wsHandle__ = wsHandle
export { startIlinkPollerIfEnabled } from "./ilink-poller.js"
export { createProductionWiring } from "./bootstrap-wiring.js"
export { runCliGoal, defaultCliConversationId } from "./cli-run.js"
export default app
