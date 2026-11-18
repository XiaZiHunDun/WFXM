#!/usr/bin/env node
/**
 * Smoke: healthz → wechat inbound (hyphenated projectId) → owner conversations list.
 * Usage: node scripts/cutover/smoke-multi-project.mjs [--api http://127.0.0.1:3000]
 */
const defaultApi = "http://127.0.0.1:3000"
let api = defaultApi
const apiEq = process.argv.find((a) => a.startsWith("--api="))
if (apiEq) {
  api = apiEq.slice("--api=".length)
} else {
  const idx = process.argv.indexOf("--api")
  if (idx >= 0 && process.argv[idx + 1]) {
    api = process.argv[idx + 1]
  }
}

const base = api.replace(/\/$/, "")
const projectId = "proj-x"
const fromUserId = `smoke-${Date.now()}`
const messageId = `smoke-msg-${Date.now()}`

function fail(step, detail) {
  console.error(`smoke FAIL [${step}]: ${detail}`)
  process.exit(1)
}

async function main() {
  const health = await fetch(`${base}/healthz`)
  const healthText = await health.text()
  if (!health.ok) fail("healthz", `${health.status} ${healthText}`)
  console.log(`smoke ok [healthz]: ${healthText}`)

  const inbound = await fetch(`${base}/v1/wechat/inbound`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      apiVersion: "v1",
      fromUserId,
      content: "smoke multi-project ping",
      messageId,
      projectId,
    }),
  })
  const inboundBody = await inbound.text()
  if (!inbound.ok) fail("wechat/inbound", `${inbound.status} ${inboundBody}`)
  let inboundJson
  try {
    inboundJson = JSON.parse(inboundBody)
  } catch {
    fail("wechat/inbound", `invalid json: ${inboundBody}`)
  }
  const conversationId = inboundJson.conversationId
  if (typeof conversationId !== "string" || !conversationId.startsWith("c-")) {
    fail("wechat/inbound", `missing conversationId in ${inboundBody}`)
  }
  console.log(`smoke ok [wechat/inbound]: conversationId=${conversationId}`)

  const list = await fetch(
    `${base}/v1/owner/conversations?projectId=${encodeURIComponent(projectId)}&limit=20`,
  )
  const listText = await list.text()
  if (!list.ok) fail("owner/conversations", `${list.status} ${listText}`)
  let listJson
  try {
    listJson = JSON.parse(listText)
  } catch {
    fail("owner/conversations", `invalid json: ${listText}`)
  }
  const ids = (listJson.items ?? []).map((i) => i.id)
  if (!ids.includes(conversationId)) {
    fail("owner/conversations", `expected ${conversationId} in items: ${listText}`)
  }
  console.log(`smoke ok [owner/conversations]: found ${conversationId} among ${ids.length} row(s)`)
  console.log("smoke PASS")
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
