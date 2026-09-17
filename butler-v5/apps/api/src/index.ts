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
import { startAutoPromoteSweeperIfEnabled } from "./auto-promote-sweeper.js"
import { parseAutoPromoteConfig } from "./auto-promote-config.js"
import { isSubagentEnabled } from "./subagent-config.js"
import {
  formatAutoPromoteNotify,
  formatCandidateExpiresNotify,
  isSweeperNotifyEnabled,
  pushSweeperNotify,
  resolveSweeperNotifyOwner,
} from "./wechat-sweeper-notify.js"

// D60 T4.4 (audit #1 F-09/F-24/F-25) + D63 T4 (audit #9 F-08): Hono app
// has no bodyLimit configured. Routes that accept body.text / body.content
// (documents.ts, memories.ts, project-knowledge.ts) let the full body into
// memory before the inner domain validator (500K / 4000 / 100K char)
// rejects. Risk is memory pressure (a 10GB POST would buffer before the
// inner validator sees it). Apply a custom Content-Length check middleware
// that rejects oversized bodies at the HTTP layer before buffering. The
// 2 MiB cap is generous for the largest documented content limit (memory
// 4K chars; documents 500K chars; project-knowledge 100K chars). Per-route
// limits are more surgical but require touching 4 files — defer to D64.
// D69 T4 (audit #10 SEC-4/SEC-10): also reject Transfer-Encoding: chunked
// (and any request without Content-Length on body-bearing methods) since
// we cannot stream-count bytes through Hono v4 middleware at this layer
// — refuse chunked up front rather than allow unbounded buffering.
const MAX_BODY_BYTES = 2 * 1024 * 1024
const app = new Hono()
app.use("*", async (c, next) => {
  const method = c.req.method.toUpperCase()
  const hasBody = method === "POST" || method === "PUT" || method === "PATCH"
  if (hasBody) {
    const contentLengthHeader = c.req.header("content-length")
    const transferEncoding = c.req.header("transfer-encoding") ?? ""
    if (transferEncoding.toLowerCase().includes("chunked") || contentLengthHeader === null) {
      return c.text("chunked / unknown-length bodies not allowed (Content-Length required)", 411)
    }
    const declared = Number(contentLengthHeader)
    if (Number.isFinite(declared) && declared > MAX_BODY_BYTES) {
      return c.text("request body too large", 413)
    }
  }
  await next()
})

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

// C 方向 推 3: sweeper → wechat push hooks (opt-in via env).
// Each sweeper carries its own notify callback; the sweeper already wraps
// notify errors so a failing push never blocks the tick.
const sweeperNotifyEnabled = isSweeperNotifyEnabled(process.env)
const sweeperNotifyOwner = resolveSweeperNotifyOwner(process.env)

const candidateExpiresNotify = async (result: {
  readonly expired: number
  readonly scanned: number
}): Promise<void> => {
  const text = formatCandidateExpiresNotify({
    expired: result.expired,
    scanned: result.scanned,
  })
  if (!text || !sweeperNotifyOwner) return
  await pushSweeperNotify({
    type: "candidate_expires",
    to: sweeperNotifyOwner,
    text,
    env: process.env,
    channels: wiring.channels,
  })
}

const candidateExpiresHandle = startCandidateExpiresSweeperIfEnabled({
  wiring,
  env: process.env,
  ...(sweeperNotifyEnabled ? { notify: candidateExpiresNotify } : {}),
})
if (candidateExpiresHandle) {
  // eslint-disable-next-line no-console -- operator log when no logger injected
  console.error("[butler-v5] candidate-expires sweeper started")
}

// G4: candidate auto-promote sweeper
const autoPromoteCfg = parseAutoPromoteConfig(process.env)
const autoPromoteNotify = async (result: {
  readonly promoted: number
  readonly scanned: number
}): Promise<void> => {
  const text = formatAutoPromoteNotify({
    promoted: result.promoted,
    scanned: result.scanned,
  })
  if (!text || !sweeperNotifyOwner) return
  await pushSweeperNotify({
    type: "auto_promote",
    to: sweeperNotifyOwner,
    text,
    env: process.env,
    channels: wiring.channels,
  })
}
const autoPromoteHandle = startAutoPromoteSweeperIfEnabled({
  wiring,
  config: autoPromoteCfg,
  ...(sweeperNotifyEnabled ? { notify: autoPromoteNotify } : {}),
})
if (autoPromoteHandle) {
  // eslint-disable-next-line no-console -- operator log when no logger injected
  console.error("[butler-v5] auto-promote sweeper started")
}

const shutdown = (): void => {
  scheduleHandle?.stop()
  projectKnowledgeWatchHandle?.stop()
  candidateExpiresHandle?.stop()
  autoPromoteHandle?.stop()
  stopSubagent?.()
  void wsHandle?.close()
  void boot.value.close()
}
process.on("SIGINT", shutdown)
process.on("SIGTERM", shutdown)

// D60 T5.2 (audit #2 F-09): barrel re-export cleanup. Only 3 exports
// have external consumers — `default` (Hono app, used by cli + 2 e2e tests),
// `__wiring__` (used by 2 e2e tests), and `startIlinkPollerIfEnabled`
// (used by cli). All other re-exports accumulate into a public API
// surface nobody consumes — drop 11 dead re-exports.
export const __wiring__ = wiring
export { startIlinkPollerIfEnabled } from "./ilink-poller.js"
export default app
