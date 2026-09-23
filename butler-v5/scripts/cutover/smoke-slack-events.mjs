#!/usr/bin/env node
/**
 * F4 fix (D81): Slack events smoke (loopback, asserts handler wiring).
 *
 * Exercises the three documented Slack handler paths in
 * `apps/api/src/routes/slack-events.ts`:
 *   1. url_verification challenge (no signature required per Slack docs)
 *   2. event_callback with HMAC-SHA256 signature (5-min replay window,
 *      timing-safe compare via packages/adapters/src/slack/slack-protocol.ts)
 *   3. invalid signature rejection (FAIL-CLOSED smoke gate)
 *
 * Requires gateway with:
 *   BUTLER_V5_SLACK_ENABLED=1
 *   BUTLER_V5_SLACK_SIGNING_SECRET=<shared secret for HMAC>
 *   BUTLER_V5_SLACK_BOT_TOKEN=<mock token for outbound reply — mock OK,
 *     outbound fetch will fail but handler returns 200 regardless>
 */
import { createHmac } from "node:crypto"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const scriptDir = dirname(fileURLToPath(import.meta.url))
const repoRoot = join(scriptDir, "../..")
const defaultApi = "http://127.0.0.1:3000"
let api = defaultApi
const apiEq = process.argv.find((a) => a.startsWith("--api="))
if (apiEq) api = apiEq.slice("--api=".length)
const base = api.replace(/\/$/, "")
const signingSecret = (process.env["BUTLER_V5_SLACK_SIGNING_SECRET"] ?? "").trim()

function fail(step, detail) {
  console.error(`slack FAIL [${step}]: ${detail}`)
  process.exit(1)
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function postSlack(rawBody, headers = {}) {
  const res = await fetch(`${base}/v1/channel/slack/events`, {
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
  if (!signingSecret) {
    fail("env", "BUTLER_V5_SLACK_SIGNING_SECRET unset")
  }

  if (!(await fetch(`${base}/healthz`)).ok) fail("healthz", "down")
  console.log("slack ok [healthz]")

  // Test 1: url_verification challenge (no signature required).
  // Per slack-events.ts:46-47, signature check is intentionally skipped
  // for `kind === "challenge"` (Slack onboarding handshake).
  const challengePayload = {
    type: "url_verification",
    challenge: "smoke-test-challenge-D81-F4",
  }
  const challengeResult = await postSlack(JSON.stringify(challengePayload))
  if (challengeResult.status !== 200) {
    fail("url-verification", `expected 200, got ${challengeResult.status}: ${challengeResult.text}`)
  }
  if (challengeResult.json?.challenge !== "smoke-test-challenge-D81-F4") {
    fail(
      "url-verification",
      `expected challenge echo, got ${JSON.stringify(challengeResult.json)}`,
    )
  }
  console.log("slack ok [url-verification]")

  // Test 2: event_callback with valid signature. HMAC over v0:{ts}:{rawBody}.
  const timestamp = Math.floor(Date.now() / 1000).toString()
  const eventPayload = {
    type: "event_callback",
    team_id: "T-CI-SMOKE",
    event_id: "Ev-CI-SMOKE-1",
    event: {
      type: "message",
      text: "hello from slack smoke",
      channel: "C-CI-SMOKE",
      user: "U-CI-SMOKE",
      ts: "1234567890.123456",
    },
  }
  const rawBody = JSON.stringify(eventPayload)
  const sigBase = `v0:${timestamp}:${rawBody}`
  const sig = "v0=" + createHmac("sha256", signingSecret).update(sigBase).digest("hex")

  const eventResult = await postSlack(rawBody, {
    "x-slack-signature": sig,
    "x-slack-request-timestamp": timestamp,
  })
  if (eventResult.status !== 200) {
    fail(
      "event-callback",
      `expected 200, got ${eventResult.status}: ${eventResult.text}`,
    )
  }
  if (!eventResult.json?.ok) {
    fail("event-callback", `expected ok=true: ${eventResult.text}`)
  }
  if (typeof eventResult.json?.reply !== "string") {
    fail("event-callback", `expected reply string: ${eventResult.text}`)
  }
  console.log("slack ok [event-callback]")

  // Test 3: invalid signature rejection (FAIL-CLOSED smoke gate).
  const invalidResult = await postSlack(rawBody, {
    "x-slack-signature": "v0=deadbeef",
    "x-slack-request-timestamp": timestamp,
  })
  if (invalidResult.status !== 401) {
    fail(
      "invalid-signature",
      `expected 401 FAIL-CLOSED, got ${invalidResult.status}: ${invalidResult.text}`,
    )
  }
  console.log("slack ok [invalid-signature-401]")

  console.log(`slack PASS`)
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})