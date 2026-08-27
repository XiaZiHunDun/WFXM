#!/usr/bin/env node
/**
 * Smoke: Task / Memory / Quality gate WeChat commands.
 */
const defaultApi = "http://127.0.0.1:3000"
let api = defaultApi
const apiEq = process.argv.find((a) => a.startsWith("--api="))
if (apiEq) api = apiEq.slice("--api=".length)
const base = api.replace(/\/$/, "")
const fromUserId = `cmd-smoke-${Date.now()}`

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

  const remember = await inbound("/记住 smoke: Butler v5 微信命令验收标记")
  if (!String(remember.reply).includes("已记住")) fail("/记住", remember.reply)
  console.log("smoke ok [/记住]")

  const memories = await inbound("/记忆")
  if (!String(memories.reply).includes("验收标记")) fail("/记忆", memories.reply)
  console.log("smoke ok [/记忆]")

  const add = await inbound("/待办 新增 smoke 待办项 | 仅验收")
  if (!String(add.reply).includes("已添加待办")) fail("/待办 新增", add.reply)
  const taskToken = String(add.reply).match(/([0-9a-f]{8})/)?.[1]
  if (!taskToken) fail("/待办 新增/token", add.reply)
  console.log(`smoke ok [/待办 新增]: ${taskToken}`)

  const list = await inbound("/待办")
  if (!String(list.reply).includes(taskToken)) fail("/待办", list.reply)
  console.log("smoke ok [/待办]")

  const done = await inbound(`/完成 ${taskToken}`)
  if (!String(done.reply).includes("已标记完成")) fail("/完成", done.reply)
  console.log("smoke ok [/完成]")

  const gate = await inbound("/验 surface-test")
  if (!String(gate.reply).includes("质量门禁")) fail("/验", gate.reply)
  console.log(`smoke ok [/验]: ${String(gate.reply).split("\n")[1] ?? ""}`)

  console.log("smoke PASS")
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
