#!/usr/bin/env node
/**
 * R8.x.9 candidate 2 — live end-to-end test of the
 * subagent → WS push flow.
 *
 * Sequence under test:
 *   1. POST /v1/wechat/inbound with a "delegate" task → 201 +
 *      conversationId + a parent reply that mentions "委派".
 *   2. WS client opens ws://127.0.0.1:3002/v1/ws?conversationId=<id>
 *      AFTER the HTTP response is back. The /v1/wechat/inbound
 *      handler is synchronous-ish — the parent butler loop completes
 *      before HTTP returns, but the subagent reply is written by
 *      the polling worker (5s tick) after the request lands.
 *   3. Subagent worker fires AssistantMessageProduced → server
 *      calls `pushEventToSubscribers(parentConversationId, event)`
 *      which writes a `{kind:"event", ...}` frame to every
 *      subscribed socket.
 *   4. WS client receives the event frame within 30s.
 *
 * Exits:
 *   0 — subagent reply received within 30s
 *   1 — pre-flight check failed (no conversationId / reply didn't
 *       mention "委派" / WS not reachable / no event ever arrived)
 *   2 — fatal runtime error
 *
 * Notes:
 *   - Path MUST be /v1/ws on port 3002 (WS_PORT in the systemd
 *     unit); the upgrade handler in ws-routes.ts destroys the
 *     socket for any other path.
 *   - Resolves `ws` via the apps/api workspace so the smoke test
 *     runs under system Node without pnpm install at repo root.
 *   - The "connected" greeting arrives first, then any number of
 *     `event` frames. We pass when at least one `event` frame
 *     carries an `AssistantMessageProduced` marker (either at the
 *     envelope level or nested under `event.eventType`).
 */

import { createRequire } from "node:module"
import { spawnSync } from "node:child_process"
import { dirname, join, resolve } from "node:path"
import { fileURLToPath } from "node:url"

const HOST = "127.0.0.1"
const HTTP_PORT = 3000
const WS_PORT = Number(process.env["WS_PORT"] ?? 3002)
const V5_URL = `http://${HOST}:${HTTP_PORT}/v1/wechat/inbound`
const WS_URL = `ws://${HOST}:${WS_PORT}/v1/ws`

const HARD_TIMEOUT_MS = 30_000

// Resolve `ws` from the apps/api workspace.
const here = dirname(fileURLToPath(import.meta.url))
const appsApiWsDir = resolve(join(here, "..", "..", "apps", "api"))
const req = createRequire(join(appsApiWsDir, "package.json"))
const WebSocket = req("ws")

const start = Date.now()
function t() {
  return `${Date.now() - start}ms`
}
function log(line) {
  process.stdout.write(`${line}\n`)
}

function curlJson(url, body) {
  const args = [
    "-s",
    "-w",
    "\n%{http_code}",
    "-X",
    "POST",
    "-H",
    "content-type: application/json",
    "-d",
    JSON.stringify(body),
    url,
  ]
  const res = spawnSync("curl", args, { encoding: "utf8" })
  if (res.status !== 0) {
    return { ok: false, reason: `curl exit ${res.status}: ${res.stderr}` }
  }
  const out = res.stdout
  const lastNl = out.lastIndexOf("\n")
  const statusLine = out.slice(lastNl + 1).trim()
  const bodyStr = out.slice(0, lastNl)
  let parsed
  try {
    parsed = JSON.parse(bodyStr)
  } catch {
    return { ok: false, reason: `curl response not JSON: ${bodyStr.slice(0, 200)}` }
  }
  return { ok: true, status: Number(statusLine), body: parsed }
}

function frameMentionsAssistantProduced(text) {
  // Frame is JSON; we test both envelope-level and nested shapes
  // because subagent-worker.ts pushes a nested object.
  if (typeof text !== "string") return false
  if (!text.includes("AssistantMessageProduced")) return false
  // Cheap double-check that the marker is not just a stray string in
  // some unrelated log line — require it to look like JSON.
  if (!text.includes('"kind":"event"')) return false
  return true
}

async function main() {
  log(`[+] ${t()} POST ${V5_URL} (delegate test)`)
  const inbox = curlJson(V5_URL, {
    apiVersion: "v1",
    fromUserId: "r8x9-e2e-test",
    content: "委派一个简单任务给 general 子代理，要求调用 get_current_time 工具获取当前时间",
    projectId: "r8x9-e2e",
  })
  if (!inbox.ok) {
    console.error(`[!] HTTP call failed: ${inbox.reason}`)
    process.exit(1)
  }
  log(`[+] ${t()} inbox status=${inbox.status} conversationId=${inbox.body?.conversationId}`)
  log(`[+] ${t()} inbox reply: ${JSON.stringify(inbox.body).slice(0, 240)}...`)

  if (!inbox.body?.conversationId || typeof inbox.body.conversationId !== "string") {
    console.error(`[!] no conversationId in inbox reply`)
    process.exit(1)
  }
  if (!inbox.body?.reply || !inbox.body.reply.includes("委派")) {
    console.error(
      `[!] inbox reply doesn't mention 委派: ${(inbox.body?.reply ?? "").slice(0, 120)}`,
    )
    process.exit(1)
  }

  const conversationId = inbox.body.conversationId
  const wsUrl = `${WS_URL}?conversationId=${conversationId}`
  log(`[+] ${t()} WS connect to ${wsUrl}`)

  const events = []
  let resolved = false
  const ws = new WebSocket(wsUrl)

  const hardKill = setTimeout(() => {
    if (resolved) return
    resolved = true
    log(`\n[${t()}] TIMEOUT after ${HARD_TIMEOUT_MS}ms — received ${events.length} events:`)
    for (const e of events) log(`  - @${e.at}ms kind=${e.kind}: ${e.data.slice(0, 200)}`)
    try {
      ws.close()
    } catch {
      // best-effort
    }
    process.exit(1)
  }, HARD_TIMEOUT_MS)

  ws.on("open", () => {
    events.push({ at: Date.now() - start, kind: "open", data: "WS handshake complete" })
    log(`[+] ${t()} WS open (events=${events.length})`)
  })

  ws.on("message", (raw) => {
    const str = raw.toString()
    let kind = "message"
    try {
      const parsed = JSON.parse(str)
      if (parsed && typeof parsed === "object" && typeof parsed.kind === "string") {
        kind = parsed.kind
      }
    } catch {
      // raw text, not JSON — leave kind=message
    }
    events.push({ at: Date.now() - start, kind, data: str })
    log(`[+] ${t()} WS recv kind=${kind}: ${str.slice(0, 220)}`)
    if (frameMentionsAssistantProduced(str)) {
      resolved = true
      clearTimeout(hardKill)
      try {
        ws.close()
      } catch {
        // best-effort
      }
      log(`\n[${t()}] OK — subagent→WS push verified (received ${events.length} frames)`)
      setTimeout(() => process.exit(0), 200)
    }
  })

  ws.on("error", (err) => {
    log(`[!] ${t()} WS error: ${err?.message ?? String(err)}`)
    if (!resolved) {
      resolved = true
      clearTimeout(hardKill)
      try {
        ws.close()
      } catch {
        // best-effort
      }
      process.exit(1)
    }
  })

  ws.on("close", (code, reason) => {
    events.push({
      at: Date.now() - start,
      kind: "close",
      data: `code=${code} reason=${reason ? reason.toString() : ""}`,
    })
    log(`[+] ${t()} WS close code=${code} reason=${reason ? reason.toString() : ""}`)
    if (!resolved) {
      // WS dropped before we got the subagent reply — count as fail.
      resolved = true
      clearTimeout(hardKill)
      console.error(`[!] WS closed before subagent push arrived`)
      process.exit(1)
    }
  })
}

main().catch((err) => {
  console.error(`[!] fatal:`, err)
  process.exit(2)
})
