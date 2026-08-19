#!/usr/bin/env node
/**
 * OpenClaw mock service for R8.x v5 wechat-gateway Phase 3 testing.
 *
 * v4 wechat-gateway normally connects to real OpenClaw iLink Bot API
 * (long-poll getupdates + send message). This mock implements the
 * minimal iLink HTTP surface so v4 wechat-gateway can run end-to-end
 * without real OpenClaw.
 *
 * Endpoints (per v4 butler/gateway/platforms/wechat_ilink/transport.py):
 *   POST /ilink/bot/getupdates       — long-poll, returns queued messages
 *   POST /ilink/bot/sendmessage      — accepts v4 outbound replies
 *   POST /ilink/bot/sendtyping       — typing indicator (no-op)
 *   POST /ilink/bot/getconfig        — bot config (no-op)
 *   POST /ilink/bot/getuploadurl     — media upload URL (no-op)
 *   POST /ilink/bot/get_bot_qrcode   — QR (no-op)
 *   POST /ilink/bot/get_qrcode_status — QR status (no-op)
 *
 * Pre-loaded messages can be pushed via POST /admin/push with a JSON body.
 * v4 outbound replies are logged to /tmp/openclaw-mock-outbox.jsonl.
 *
 * Usage:
 *   node openclaw-mock.mjs                  # default port 9999
 *   PORT=8888 node openclaw-mock.mjs       # custom port
 *   ILINK_BASE_URL=http://127.0.0.1:9999  # tell v4 to use this mock
 *
 * Owner: run this, then run v4 butler-gateway.service with
 * ILINK_BASE_URL env var pointing here.
 */

import http from "node:http"
import fs from "node:fs"

const PORT = Number(process.env.PORT || 9999)
const OUTBOX_PATH = process.env.OUTBOX_PATH || "/tmp/openclaw-mock-outbox.jsonl"
const SYNC_BUF = process.env.SYNC_BUF || "mock-sync-buf-0"

// Pre-loaded message queue (FIFO). v4 wechat-gateway long-polls and
// drains this queue one message per getupdates call.
const messageQueue = []
let nextSyncBuf = SYNC_BUF

function readJsonBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = []
    req.on("data", (c) => chunks.push(c))
    req.on("end", () => {
      const raw = Buffer.concat(chunks).toString("utf8")
      if (!raw) return resolve({})
      try {
        resolve(JSON.parse(raw))
      } catch (e) {
        reject(e)
      }
    })
    req.on("error", reject)
  })
}

function sendJson(res, status, body) {
  const text = JSON.stringify(body)
  res.writeHead(status, {
    "content-type": "application/json",
    "content-length": Buffer.byteLength(text),
  })
  res.end(text)
}

function extractSendText(msg) {
  const items = msg.item_list || []
  for (const it of items) {
    if (it && (it.type === "text" || it.type === 1)) {
      return it.text_item?.text || it.text_item?.content || it.text || ""
    }
  }
  return items[0]?.text || ""
}

function sendEmptyOk(res) {
  res.writeHead(200, { "content-length": "2" })
  res.end("ok")
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || "localhost"}`)
  const path = url.pathname
  const method = req.method || "GET"

  try {
    // --- iLink surface ---
    if (path === "/ilink/bot/getupdates" && method === "POST") {
      const body = await readJsonBody(req)
      const buf = body.get_updates_buf ?? nextSyncBuf
      const msg = messageQueue.shift() ?? null
      // Per v4 transport._get_updates: return {ret, msgs, get_updates_buf}
      return sendJson(res, 200, {
        ret: 0,
        errcode: 0,
        errmsg: "ok",
        msgs: msg ? [msg] : [],
        get_updates_buf: buf,
      })
    }

    if (path === "/ilink/bot/sendmessage" && method === "POST") {
      const body = await readJsonBody(req)
      const msg = body.msg || {}
      // Log to outbox for owner to inspect
      const entry = {
        ts: new Date().toISOString(),
        to_user_id: msg.to_user_id,
        text: extractSendText(msg),
        context_token: msg.context_token,
        client_id: msg.client_id,
      }
      fs.appendFileSync(OUTBOX_PATH, JSON.stringify(entry) + "\n")
      console.log(`[mock] sendmessage to=${entry.to_user_id} text=${entry.text.slice(0, 80)}`)
      return sendJson(res, 200, { ret: 0, errcode: 0, errmsg: "ok" })
    }

    if (path === "/ilink/bot/sendtyping" && method === "POST") {
      // typing indicator — no-op
      return sendEmptyOk(res)
    }

    if (path === "/ilink/bot/getconfig" && method === "POST") {
      // v4 reads this at startup; return minimal valid config
      return sendJson(res, 200, {
        ret: 0,
        errcode: 0,
        errmsg: "ok",
        iLink_config: { ilink_app_client_version: "mock-1.0" },
      })
    }

    if (path === "/ilink/bot/getuploadurl" && method === "POST") {
      // media upload — return a fake CDN URL (v4 won't actually use this
      // in our test since we don't send media)
      return sendJson(res, 200, {
        ret: 0,
        errcode: 0,
        upload_url: `http://127.0.0.1:${PORT}/mock-cdn-upload`,
      })
    }

    if (path === "/ilink/bot/get_bot_qrcode" && method === "POST") {
      // QR code generation — return a fake PNG
      return sendJson(res, 200, { ret: 0, qrcode_img: "iVBORw0KGgo=" })
    }

    if (path === "/ilink/bot/get_qrcode_status" && method === "POST") {
      // QR status — already-scanned
      return sendJson(res, 200, {
        ret: 0,
        errcode: 0,
        status: 2, // scanned & confirmed
        ilink_user_id: "mock-v4-bot-account",
      })
    }

    // --- admin surface (for owner testing) ---
    if (path === "/admin/push" && method === "POST") {
      const body = await readJsonBody(req)
      // Push a fake incoming wechat message into the queue
      const msg = {
        msg_id: `mock-msg-${Date.now()}`,
        from_user_id: body.from_user_id || "wechat-mock-user",
        to_user_id: body.to_user_id || "mock-v4-bot-account",
        create_time: Math.floor(Date.now() / 1000),
        message_type: 1, // text
        message_state: 2,
        item_list: [
          {
            type: "text",
            text_item: {
              content: body.content || "(empty)",
            },
          },
        ],
      }
      if (body.context_token) msg.context_token = body.context_token
      messageQueue.push(msg)
      console.log(
        `[mock] queued message from=${msg.from_user_id} content=${msg.content_item?.content || body.content}`,
      )
      return sendJson(res, 200, {
        queued: true,
        msg_id: msg.msg_id,
        queue_size: messageQueue.length,
      })
    }

    if (path === "/admin/queue" && method === "GET") {
      return sendJson(res, 200, { queue_size: messageQueue.length, messages: messageQueue })
    }

    if (path === "/admin/clear" && method === "POST") {
      const n = messageQueue.length
      messageQueue.length = 0
      return sendJson(res, 200, { cleared: n })
    }

    if (path === "/admin/outbox" && method === "GET") {
      // Return last 50 lines of outbox
      let data = ""
      try {
        data = fs.readFileSync(OUTBOX_PATH, "utf8")
      } catch (e) {
        return sendJson(res, 200, { error: String(e), outbox_path: OUTBOX_PATH })
      }
      const lines = data.trim().split("\n").slice(-50)
      return sendJson(res, 200, { outbox: lines })
    }

    if (path === "/" || path === "/health") {
      return sendJson(res, 200, {
        status: "ok",
        service: "openclaw-mock",
        port: PORT,
        queue_size: messageQueue.length,
        outbox_path: OUTBOX_PATH,
      })
    }

    // 404 for everything else
    res.writeHead(404, { "content-type": "application/json" })
    res.end(JSON.stringify({ error: "not found", path }))
  } catch (err) {
    console.error(`[mock] error: ${err}`)
    sendJson(res, 500, { error: String(err) })
  }
})

server.listen(PORT, "127.0.0.1", () => {
  console.log(`[mock] OpenClaw iLink mock listening on http://127.0.0.1:${PORT}`)
  console.log(`[mock] Outbox: ${OUTBOX_PATH}`)
  console.log(`[mock] Admin: POST /admin/push {from_user_id, to_user_id, content}`)
  console.log(`[mock]         GET  /admin/queue  — view queued messages`)
  console.log(`[mock]         GET  /admin/outbox — view v4 outbound replies`)
  console.log(`[mock]         POST /admin/clear  — clear queue`)
  console.log(`[mock]         GET  /health       — status`)
})
