#!/usr/bin/env node
/**
 * Smoke: Subagent /委派 command (disabled hint or delegate ack).
 */
const defaultApi = "http://127.0.0.1:3000"
let api = defaultApi
const apiEq = process.argv.find((a) => a.startsWith("--api="))
if (apiEq) api = apiEq.slice("--api=".length)
const base = api.replace(/\/$/, "")
const fromUserId = `prod-smoke-${Date.now()}`

function fail(step, detail) {
  console.error(`smoke FAIL [${step}]: ${detail}`)
  process.exit(1)
}

async function inbound(content) {
  const res = await fetch(`${base}/v1/wechat/inbound`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      apiVersion: "v1",
      fromUserId,
      content,
      messageId: `${fromUserId}-${Date.now()}`,
      projectId: "wechat",
    }),
  })
  const text = await res.text()
  if (!res.ok) fail("inbound", `${res.status} ${text}`)
  return JSON.parse(text)
}

async function main() {
  if (!(await fetch(`${base}/healthz`)).ok) fail("healthz", "down")
  console.log("smoke ok [healthz]")

  const delegate = await inbound("/委派 smoke productivity check")
  const reply = String(delegate.reply)
  if (reply.includes("Subagent 未启用")) {
    console.log("smoke ok [/委派 disabled hint]")
  } else if (reply.includes("已委派")) {
    console.log("smoke ok [/委派 delegated]")
    const status = await inbound("/委派状态")
    if (!String(status.reply).includes("最近委派")) fail("/委派状态", status.reply)
    console.log("smoke ok [/委派状态]")
  } else {
    fail("/委派", reply)
  }

  console.log("smoke PASS")
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
