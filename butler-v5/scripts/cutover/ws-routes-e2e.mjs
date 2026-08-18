#!/usr/bin/env node
// R8.x.8 WebSocket e2e smoke test.
//
// Connects to ws://127.0.0.1:3002/v1/ws (the WS_PORT the
// butler-v5-gateway.service exports), verifies the upgrade
// handshake + the `connected` greeting, then exercises the
// ping/pong keepalive.
//
// Stays in the smoke-test lane — does not trigger a subagent
// delegation. Subagent -> WS push fan-out is already covered by
// the unit tests in apps/api/src/ws-routes.test.ts and
// apps/api/src/subagent-worker.test.ts.
//
// Notes:
//   - Path MUST be /v1/ws; the upgrade handler in ws-routes.ts
//     destroys the socket for any other path.
//   - Resolves the `ws` package via the apps/api workspace so the
//     smoke test can run under system Node without pnpm install.
//   - Exits 0 on success, 2 on timeout, 1 on error.
//
// Usage:
//   node scripts/cutover/ws-routes-e2e.mjs
//   PORT=3002 node scripts/cutover/ws-routes-e2e.mjs

import { createRequire } from "node:module"
import { dirname, join, resolve } from "node:path"
import { fileURLToPath } from "node:url"

const HOST = process.env["WS_HOST"] ?? "127.0.0.1"
const PORT = Number(process.env["WS_PORT"] ?? process.env["PORT"] ?? 3002)
const CONV = process.env["WS_CONV"] ?? "c-r8x8-ws-smoke"
const URL = `ws://${HOST}:${PORT}/v1/ws?conversationId=${CONV}`

const HARD_TIMEOUT_MS = 30_000

// Resolve `ws` from the apps/api workspace so the system node can
// load it without needing pnpm install at the repo root.
const here = dirname(fileURLToPath(import.meta.url))
const appsApiWsDir = resolve(join(here, "..", "..", "apps", "api"))
const req = createRequire(join(appsApiWsDir, "package.json"))
const WebSocket = req("ws")

const events = []
let resolved = false
let ws = null
const start = Date.now()

function log(line) {
  process.stdout.write(`${line}\n`)
}

const hardKill = setTimeout(() => {
  if (!resolved) {
    log(`TIMEOUT after ${Date.now() - start}ms (received ${events.length} events):`)
    for (const e of events) log(`  - @${e.at}ms ${e.kind}: ${e.data}`)
    if (ws && typeof ws.close === "function") {
      try {
        ws.close()
      } catch {
        // best-effort
      }
    }
    process.exit(2)
  }
}, HARD_TIMEOUT_MS)

function record(data, kind) {
  const at = Date.now() - start
  events.push({ at, kind, data })
  log(`[${events.length}] ${kind} @${at}ms: ${data}`)
}

function openOne(attempt) {
  ws = new WebSocket(URL)

  ws.on("open", () => {
    record(URL, "open")
    try {
      ws.send(JSON.stringify({ kind: "ping" }))
      record("sent ping", "send")
    } catch (err) {
      record(`send failed: ${err && err.message ? err.message : String(err)}`, "error")
    }
  })

  ws.on("message", (raw) => {
    const str = raw.toString()
    let kind = "message"
    let parsedKind = ""
    try {
      const parsed = JSON.parse(str)
      if (parsed && typeof parsed === "object" && typeof parsed.kind === "string") {
        kind = parsed.kind
        parsedKind = parsed.kind
      }
    } catch {
      // raw text, not JSON
    }
    record(str, kind)
    if (parsedKind === "pong") {
      resolved = true
      clearTimeout(hardKill)
      try {
        ws.close()
      } catch {
        // best-effort
      }
      setTimeout(() => {
        log(`\nOK: connected + ping/pong verified in ${Date.now() - start}ms`)
        log(`Total events: ${events.length}`)
        process.exit(0)
      }, 200)
      return
    }
  })

  ws.on("error", (err) => {
    record(`error: ${err && err.message ? err.message : String(err)}`, "error")
    if (!resolved && attempt < 2) {
      log(`retrying in 500ms (attempt ${attempt + 1})...`)
      setTimeout(() => openOne(attempt + 1), 500)
      return
    }
    if (!resolved) {
      clearTimeout(hardKill)
      process.exit(1)
    }
  })

  ws.on("close", (code, reason) => {
    record(`close code=${code} reason=${reason ? reason.toString() : ""}`, "close")
    if (!resolved && attempt < 2) {
      log(`retrying after close in 500ms (attempt ${attempt + 1})...`)
      setTimeout(() => openOne(attempt + 1), 500)
      return
    }
    if (!resolved) {
      clearTimeout(hardKill)
      process.exit(2)
    }
  })
}

log(`Connecting to ${URL}`)
openOne(1)
