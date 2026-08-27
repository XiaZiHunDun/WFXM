#!/usr/bin/env node
/**
 * L3 iLink connectivity — minimal real-device substitute.
 *
 * Default: POST getupdates (proves token + API reachability, no user message).
 * Optional: --send-ping sends one line to BUTLER_V5_ILINK_PING_TO (real WeChat).
 *
 * Reads ~/.config/butler-v5/env when WECHAT_TOKEN not in process.env.
 */
import { readFileSync } from "node:fs"
import { homedir } from "node:os"
import { join } from "node:path"

const ILINK_APP_ID = "bot"
const CHANNEL_VERSION = "2.2.0"
const ILINK_APP_CLIENT_VERSION = (2 << 16) | (2 << 8) | 0
const MSG_TYPE_BOT = 2
const MSG_STATE_FINISH = 2
const ITEM_TEXT = 1
const DEFAULT_BASE = "https://ilinkai.weixin.qq.com"
const ENV_FILE = join(homedir(), ".config", "butler-v5", "env")

const sendPing = process.argv.includes("--send-ping")

function fail(step, detail) {
  console.error(`ilink smoke FAIL [${step}]: ${detail}`)
  process.exit(1)
}

function loadEnvFile() {
  try {
    const lines = readFileSync(ENV_FILE, "utf8").split("\n")
    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed || trimmed.startsWith("#")) continue
      const eq = trimmed.indexOf("=")
      if (eq <= 0) continue
      const key = trimmed.slice(0, eq)
      let val = trimmed.slice(eq + 1)
      if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
        val = val.slice(1, -1)
      }
      if (process.env[key] === undefined) process.env[key] = val
    }
  } catch {
    // optional file
  }
}

function ilinkHeaders(token) {
  return {
    "Content-Type": "application/json",
    AuthorizationType: "ilink_bot_token",
    "iLink-App-Id": ILINK_APP_ID,
    "iLink-App-ClientVersion": String(ILINK_APP_CLIENT_VERSION),
    Authorization: `Bearer ${token}`,
    "X-WECHAT-UIN": String(Math.floor(Math.random() * 1_000_000_000)),
  }
}

async function ilinkPost(baseUrl, token, endpoint, body, timeoutMs) {
  const url = `${baseUrl.replace(/\/+$/, "")}/${endpoint}`
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: ilinkHeaders(token),
      body: JSON.stringify(body),
      signal: ctrl.signal,
    })
    const raw = await res.text()
    if (!res.ok) fail("http", `${endpoint} ${res.status} ${raw.slice(0, 200)}`)
    let parsed
    try {
      parsed = JSON.parse(raw)
    } catch {
      fail("json", raw.slice(0, 200))
    }
    return parsed
  } catch (err) {
    if (err instanceof Error && (err.name === "AbortError" || err.name === "TimeoutError")) {
      return { ret: 0, _timeout: true }
    }
    fail("fetch", err instanceof Error ? err.message : String(err))
  } finally {
    clearTimeout(timer)
  }
}

async function main() {
  loadEnvFile()
  const enabled = (process.env["BUTLER_V5_ILINK_ENABLED"] ?? "").trim()
  if (enabled !== "1" && enabled.toLowerCase() !== "true") {
    fail("config", "BUTLER_V5_ILINK_ENABLED is not set")
  }
  const token = (process.env["WECHAT_TOKEN"] ?? "").trim()
  if (!token) fail("config", "WECHAT_TOKEN missing")
  const baseUrl = (process.env["WECHAT_BASE_URL"] ?? process.env["ILINK_BASE_URL"] ?? DEFAULT_BASE).trim()

  const updates = await ilinkPost(
    baseUrl,
    token,
    "ilink/bot/getupdates",
    { get_updates_buf: "", base_info: { channel_version: CHANNEL_VERSION } },
    8_000,
  )
  const ret = updates.ret
  if (ret !== 0 && ret !== undefined && !updates._timeout) {
    fail("getupdates", `ret=${ret} err=${updates.errmsg ?? updates.err_msg ?? "unknown"}`)
  }
  console.log(
    `ilink smoke ok [getupdates]: baseUrl=${baseUrl} ret=${ret ?? "timeout-empty"} msgs=${(updates.msgs ?? []).length}`,
  )

  if (sendPing) {
    const to = (process.env["BUTLER_V5_ILINK_PING_TO"] ?? "").trim()
    if (!to) {
      fail("send-ping", "set BUTLER_V5_ILINK_PING_TO to a WeChat user id for --send-ping")
    }
    const text = `[butler-v5 连通性探测 ${new Date().toISOString().slice(0, 19)}]`
    const sent = await ilinkPost(
      baseUrl,
      token,
      "ilink/bot/sendmessage",
      {
        msg: {
          from_user_id: "",
          to_user_id: to,
          client_id: `v5-ping-${Date.now()}`,
          message_type: MSG_TYPE_BOT,
          message_state: MSG_STATE_FINISH,
          item_list: [{ type: ITEM_TEXT, text_item: { text } }],
        },
        base_info: { channel_version: CHANNEL_VERSION },
      },
      15_000,
    )
    if (sent.ret !== 0 && sent.ret !== undefined) {
      fail("sendmessage", `ret=${sent.ret} err=${sent.errmsg ?? sent.err_msg ?? "unknown"}`)
    }
    console.log(`ilink smoke ok [send-ping]: to=${to}`)
  } else {
    console.log("ilink smoke skip [send-ping]: use --send-ping + BUTLER_V5_ILINK_PING_TO for outbound probe")
  }

  console.log("ilink smoke PASS")
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
