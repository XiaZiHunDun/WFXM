#!/usr/bin/env node
/**
 * Smoke: two WeChat turns on the same conversation stream → relational messages grow.
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
const projectId = "proj-x"
const fromUserId = `context-smoke-${Date.now()}`
const expectedConversationId = `c-${projectId}-${fromUserId}`

function fail(step, detail) {
  console.error(`smoke FAIL [${step}]: ${detail}`)
  process.exit(1)
}

async function postInbound(content, messageId) {
  const res = await fetch(`${base}/v1/wechat/inbound`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      apiVersion: "v1",
      fromUserId,
      content,
      messageId,
      projectId,
    }),
  })
  const text = await res.text()
  if (!res.ok) fail("wechat/inbound", `${res.status} ${text}`)
  const json = JSON.parse(text)
  if (json.conversationId !== expectedConversationId) {
    fail("wechat/inbound", `expected ${expectedConversationId}, got ${json.conversationId}`)
  }
  return json
}

async function fetchMessages() {
  const list = await fetch(
    `${base}/v1/owner/conversations/${encodeURIComponent(expectedConversationId)}/messages?limit=30`,
  )
  const listText = await list.text()
  if (!list.ok) fail("owner/messages", `${list.status} ${listText}`)
  return JSON.parse(listText)
}

async function waitForMultiTurn(timeoutMs = 45_000) {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    const body = await fetchMessages()
    const items = body.items ?? []
    const userTexts = items
      .filter((m) => m.role === "user")
      .map((m) => (typeof m.content?.text === "string" ? m.content.text : ""))
    const uniqueUserTexts = new Set(userTexts)
    if (uniqueUserTexts.size !== userTexts.length) {
      fail("owner/messages", `duplicate user rows: ${JSON.stringify(userTexts)}`)
    }
    const hasSecondTurn = userTexts.some((t) => t.includes("第二轮"))
    const userCount = userTexts.length
    const assistantCount = items.filter((m) => m.role === "assistant").length
    if (hasSecondTurn && userCount === 2 && assistantCount >= 1) {
      return { userCount, assistantCount, items }
    }
    await new Promise((r) => setTimeout(r, 800))
  }
  fail("owner/messages", "timed out waiting for second-turn user message in relational store")
}

async function main() {
  const health = await fetch(`${base}/healthz`)
  if (!health.ok) fail("healthz", `${health.status}`)
  console.log("smoke ok [healthz]")

  await postInbound("第一轮：记住代号 alpha", `ctx-smoke-1-${Date.now()}`)
  await postInbound("第二轮：我的代号是什么？", `ctx-smoke-2-${Date.now()}`)
  console.log(`smoke ok [wechat/inbound x2]: conversationId=${expectedConversationId}`)

  const { userCount, assistantCount } = await waitForMultiTurn()
  console.log(
    `smoke ok [owner/messages]: ${userCount} user + ${assistantCount} assistant (同一 conversationId，recall_history 可读)`,
  )
  console.log("smoke PASS")
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
