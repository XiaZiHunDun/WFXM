import { Hono } from "hono"
import { createRoutes } from "./routes.js"
import { createOwnerRoutes } from "./owner-routes.js"
import { createProductionWiring } from "./bootstrap-wiring.js"
import { pickLLMForRole } from "@butler/adapters"
import { runSubagentWorker } from "./subagent-worker.js"
import { startWsServer, type WsServerHandle } from "./ws-routes.js"
import { startScheduleWorkerIfEnabled } from "./schedule-worker.js"
import { startProjectKnowledgeWatchWorkerIfEnabled } from "./project-knowledge-watch-worker.js"
import { startCandidateExpiresSweeperIfEnabled } from "./candidate-expires-sweeper.js"
import { isSubagentEnabled } from "./subagent-config.js"

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
    `[butler-v5] MCP enabled mode=${boot.value.mcp.mode} tools=${boot.value.mcp.runtimeTools.length} servers=${boot.value.mcp.servers.length}`,
  )
}
createRoutes(app, wiring)
createOwnerRoutes(app, wiring)

const vitest = (process.env["VITEST"] ?? "").trim() !== ""
const subagentEnabled = isSubagentEnabled(process.env)
let wsHandle: WsServerHandle | undefined
let stopSubagent: (() => void) | undefined

if (subagentEnabled) {
  const wsPort = Number(process.env["WS_PORT"] ?? (vitest ? 0 : 3001))
  const wsHost = process.env["WS_HOST"] ?? "127.0.0.1"
  wsHandle = await startWsServer({ port: wsPort, host: wsHost })
  stopSubagent = runSubagentWorker(
    wiring.eventBridge,
    (env) => pickLLMForRole(env, "exec"),
    process.env,
    {
      runtimeStore: wiring.runtimeStore,
    },
  ).stop
  if (!vitest) {
    // eslint-disable-next-line no-console -- operator log when no logger injected
    console.error("[butler-v5] subagent worker + WS enabled")
  }
} else if (!vitest) {
  // eslint-disable-next-line no-console -- operator log when no logger injected
  console.error(
    "[butler-v5] subagent disabled (set BUTLER_V5_SUBAGENT_ENABLED=1 for delegate + WS push)",
  )
}

const scheduleHandle = startScheduleWorkerIfEnabled({ wiring, env: process.env })
if (scheduleHandle) {
  // eslint-disable-next-line no-console -- operator log when no logger injected
  console.error("[butler-v5] schedule worker started")
}

const projectKnowledgeWatchHandle = startProjectKnowledgeWatchWorkerIfEnabled({
  wiring,
  env: process.env,
})
if (projectKnowledgeWatchHandle) {
  // eslint-disable-next-line no-console -- operator log when no logger injected
  console.error("[butler-v5] project-knowledge watch worker started")
}

const candidateExpiresHandle = startCandidateExpiresSweeperIfEnabled({
  wiring,
  env: process.env,
})
if (candidateExpiresHandle) {
  // eslint-disable-next-line no-console -- operator log when no logger injected
  console.error("[butler-v5] candidate-expires sweeper started")
}

const shutdown = (): void => {
  scheduleHandle?.stop()
  projectKnowledgeWatchHandle?.stop()
  candidateExpiresHandle?.stop()
  stopSubagent?.()
  void wsHandle?.close()
  void boot.value.close()
}
process.on("SIGINT", shutdown)
process.on("SIGTERM", shutdown)

export const __wiring__ = wiring
export const __wsHandle__ = wsHandle
export { startIlinkPollerIfEnabled } from "./ilink-poller.js"
export { createProductionWiring } from "./bootstrap-wiring.js"
export { runCliGoal, defaultCliConversationId } from "./cli-run.js"
export { runScheduleJob } from "./schedule-run.js"
export { startScheduleWorkerIfEnabled, runScheduleTick } from "./schedule-worker.js"
export {
  startProjectKnowledgeWatchWorkerIfEnabled,
  runProjectKnowledgeWatchTick,
} from "./project-knowledge-watch-worker.js"
export {
  startCandidateExpiresSweeperIfEnabled,
  runCandidateExpiresTick,
  parseCandidateExpiresSweeperConfig,
} from "./candidate-expires-sweeper.js"
export default app
