#!/usr/bin/env node
/**
 * Smoke: WeChat project surface (/项目, /状态, /项目概况, /项目 体检, per-project tools).
 *
 *   node scripts/cutover/smoke-wechat-project-surface.mjs [--api=http://127.0.0.1:3000]
 */
const defaultApi = "http://127.0.0.1:3000"
let api = defaultApi
const apiEq = process.argv.find((a) => a.startsWith("--api="))
if (apiEq) api = apiEq.slice("--api=".length)

const base = api.replace(/\/$/, "")
const fromUserId = `surface-smoke-${Date.now()}`

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
  const hz = await fetch(`${base}/healthz`)
  if (!hz.ok) fail("healthz", String(hz.status))
  console.log("smoke ok [healthz]")

  const list = await inbound("/项目")
  if (!String(list.reply).includes("项目列表")) fail("/项目", list.reply)
  if (!String(list.reply).includes("PK")) fail("/项目/pk", list.reply)
  console.log("smoke ok [/项目]: enriched list")

  const switched = await inbound("/切换 灵文1号")
  if (!String(switched.reply).includes("已切换到项目")) fail("/切换", switched.reply)
  if (!String(switched.reply).includes("工具：")) fail("/切换/tools", switched.reply)
  console.log("smoke ok [/切换]: includes tool profile")

  const status = await inbound("/状态")
  if (!String(status.reply).includes("灵文1号")) fail("/状态", status.reply)
  if (!String(status.reply).includes("工具")) fail("/状态/tools", status.reply)
  console.log("smoke ok [/状态]: enriched")

  const overview = await inbound("/项目概况")
  if (!String(overview.reply).includes("概况")) fail("/项目概况", overview.reply)
  console.log("smoke ok [/项目概况]")

  const health = await inbound("/项目 体检")
  if (!String(health.reply).includes("体检")) fail("/项目 体检", health.reply)
  console.log("smoke ok [/项目 体检]")

  console.log("smoke PASS")
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
