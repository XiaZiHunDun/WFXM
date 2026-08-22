#!/usr/bin/env node
/**
 * Smoke: manual schedule tick via Owner API (requires BUTLER_V5_SCHEDULE_ENABLED=1).
 */
const defaultApi = "http://127.0.0.1:3000"
let api = defaultApi
const apiEq = process.argv.find((a) => a.startsWith("--api="))
if (apiEq) {
  api = apiEq.slice("--api=".length)
} else {
  const idx = process.argv.indexOf("--api")
  if (idx >= 0 && process.argv[idx + 1]) api = process.argv[idx + 1]
}

const base = api.replace(/\/$/, "")

function fail(step, detail) {
  console.error(`smoke FAIL [${step}]: ${detail}`)
  process.exit(1)
}

async function main() {
  const health = await fetch(`${base}/healthz`)
  if (!health.ok) fail("healthz", `${health.status}`)
  console.log("smoke ok [healthz]")

  const tick = await fetch(`${base}/v1/owner/schedule/tick`, { method: "POST" })
  const tickText = await tick.text()
  if (tick.status === 400 && tickText.includes("SCHEDULE_ENABLED")) {
    fail("schedule/tick", "enable BUTLER_V5_SCHEDULE_ENABLED=1 and restart gateway")
  }
  if (!tick.ok) fail("schedule/tick", `${tick.status} ${tickText}`)
  const body = JSON.parse(tickText)
  console.log(`smoke ok [schedule/tick]: stats=${JSON.stringify(body.stats)} jobs=${JSON.stringify(body.jobs)}`)
  console.log("smoke PASS")
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
