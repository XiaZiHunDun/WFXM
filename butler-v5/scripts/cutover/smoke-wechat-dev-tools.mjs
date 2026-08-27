#!/usr/bin/env node
/**
 * Smoke: dev session + intake + optional fast verify (loopback, no iLink).
 *
 * For fast verify on gateway, set:
 *   BUTLER_V5_DEV_VERIFY_CMD='["pnpm","exec","vitest","run","apps/api/src/dev-quality-gate.test.ts"]'
 */
const defaultApi = "http://127.0.0.1:3000"
let api = defaultApi
const apiEq = process.argv.find((a) => a.startsWith("--api="))
if (apiEq) api = apiEq.slice("--api=".length)
const base = api.replace(/\/$/, "")
const fromUserId = `dev-smoke-${Date.now()}`

function fail(step, detail) {
  console.error(`smoke FAIL [${step}]: ${detail}`)
  process.exit(1)
}

async function inbound(content, conversationId) {
  const res = await fetch(`${base}/v1/wechat/inbound`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      apiVersion: "v1",
      fromUserId,
      content,
      messageId: `${fromUserId}-${Date.now()}`,
      projectId: "wechat",
      ...(conversationId ? { conversationId } : {}),
    }),
  })
  const text = await res.text()
  if (!res.ok) fail("inbound", `${res.status} ${text}`)
  return JSON.parse(text)
}

async function main() {
  if (!(await fetch(`${base}/healthz`)).ok) fail("healthz", "down")
  console.log("smoke ok [healthz]")

  const devMode = await inbound("开发模式")
  if (!String(devMode.reply).includes("开发模式")) fail("dev-session", devMode.reply)
  console.log("smoke ok [dev-session]")

  const status = await inbound("/状态")
  if (!String(status.reply).includes("当前项目")) fail("/状态", status.reply)
  console.log("smoke ok [/状态]")

  const gate = await inbound("/验 surface-test")
  if (!String(gate.reply).includes("质量门禁")) fail("/验", gate.reply)
  console.log(`smoke ok [/验]: ${String(gate.reply).split("\n")[1] ?? ""}`)

  console.log("smoke PASS (dev-tools baseline)")
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
