#!/usr/bin/env node
/**
 * F4 fix (D81): Telegram webhook smoke (loopback, asserts handler wiring).
 *
 * Exercises the three documented Telegram handler paths in
 * `apps/api/src/routes/telegram-webhook.ts`:
 *   1. Update message with valid X-Telegram-Bot-Api-Secret-Token header
 *      (FAIL-CLOSED compare via channel-inbound.ts:telegramWebhookAuthorized)
 *   2. invalid secret → 401 rejection
 *   3. Replay dedup — second identical update_id returns 204 (D74 T4 SEC-001)
 *
 * Requires gateway with:
 *   BUTLER_V5_TELEGRAM_ENABLED=1
 *   BUTLER_V5_TELEGRAM_WEBHOOK_SECRET=<shared secret for header compare>
 *   BUTLER_V5_TELEGRAM_BOT_TOKEN=<mock token for outbound reply — mock OK>
 */
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const scriptDir = dirname(fileURLToPath(import.meta.url))
const repoRoot = join(scriptDir, "../..")
const defaultApi = "http://127.0.0.1:3000"
let api = defaultApi
const apiEq = process.argv.find((a) => a.startsWith("--api="))
if (apiEq) api = apiEq.slice("--api=".length)
const base = api.replace(/\/$/, "")
const webhookSecret = (process.env["BUTLER_V5_TELEGRAM_WEBHOOK_SECRET"] ?? "").trim()

function fail(step, detail) {
  console.error(`telegram FAIL [${step}]: ${detail}`)
  process.exit(1)
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function postTelegram(rawBody, headers = {}) {
  const res = await fetch(`${base}/v1/channel/telegram/webhook`, {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: rawBody,
  })
  const text = await res.text()
  let json = null
  try {
    json = JSON.parse(text)
  } catch {
    // not JSON
  }
  return { status: res.status, text, json }
}

async function main() {
  if (!webhookSecret) {
    fail("env", "BUTLER_V5_TELEGRAM_WEBHOOK_SECRET unset")
  }

  if (!(await fetch(`${base}/healthz`)).ok) fail("healthz", "down")
  console.log("telegram ok [healthz]")

  // Test 1: Update message with valid secret_token. Header name per
  // telegram-webhook.ts:36 = `x-telegram-bot-api-secret-token`.
  const updateId = Math.floor(Math.random() * 1_000_000_000) + 100_000_000
  const updatePayload = {
    update_id: updateId,
    message: {
      message_id: 1,
      from: { id: 12345, first_name: "Test", is_bot: false },
      chat: { id: 12345, type: "private" },
      date: Math.floor(Date.now() / 1000),
      text: "hello from telegram smoke",
    },
  }
  const rawBody = JSON.stringify(updatePayload)

  const updateResult = await postTelegram(rawBody, {
    "x-telegram-bot-api-secret-token": webhookSecret,
  })
  if (updateResult.status !== 200) {
    fail("update", `expected 200, got ${updateResult.status}: ${updateResult.text}`)
  }
  if (!updateResult.json?.ok) {
    fail("update", `expected ok=true: ${updateResult.text}`)
  }
  if (typeof updateResult.json?.reply !== "string") {
    fail("update", `expected reply string: ${updateResult.text}`)
  }
  console.log("telegram ok [update-message]")

  // Test 2: invalid secret_token → 401 FAIL-CLOSED.
  const invalidResult = await postTelegram(rawBody, {
    "x-telegram-bot-api-secret-token": "wrong-secret",
  })
  if (invalidResult.status !== 401) {
    fail(
      "invalid-secret",
      `expected 401 FAIL-CLOSED, got ${invalidResult.status}: ${invalidResult.text}`,
    )
  }
  console.log("telegram ok [invalid-secret-401]")

  // Test 3: replay dedup — second identical update_id returns 204 (D74 T4
  // SEC-001 mirrors ilink-poller pattern).
  const replayResult = await postTelegram(rawBody, {
    "x-telegram-bot-api-secret-token": webhookSecret,
  })
  if (replayResult.status !== 204) {
    fail(
      "replay-dedup",
      `expected 204 idempotent, got ${replayResult.status}: ${replayResult.text}`,
    )
  }
  console.log("telegram ok [replay-dedup-204]")

  console.log("telegram PASS")
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})