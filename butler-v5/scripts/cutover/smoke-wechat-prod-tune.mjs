#!/usr/bin/env node
/**
 * Loopback production-tuning smoke (no iLink device required).
 *
 * Scenarios: dev session, chat (ping), /状态, scheme B delegate (T4 live canary).
 */
const defaultApi = "http://127.0.0.1:3000"
let api = defaultApi
const apiEq = process.argv.find((a) => a.startsWith("--api="))
if (apiEq) api = apiEq.slice("--api=".length)
const base = api.replace(/\/$/, "")
const fromUserId =
  (process.env.BUTLER_OWNER_WECHAT_ID ?? "").trim() || `prod-tune-${Date.now()}`
const conversationId = `c-wechat-prod-tune-${Date.now()}`

function fail(step, detail) {
  console.error(`prod-tune FAIL [${step}]: ${detail}`)
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
      messageId: `${conversationId}-${Date.now()}`,
      projectId: "wechat",
      conversationId,
    }),
  })
  const text = await res.text()
  if (!res.ok) fail("inbound", `${res.status} ${text}`)
  return JSON.parse(text)
}

async function main() {
  if (!(await fetch(`${base}/healthz`)).ok) fail("healthz", "down")
  console.log("prod-tune ok [healthz]")

  const dev = await inbound("开发模式")
  if (!String(dev.reply).includes("开发模式")) fail("dev-session", dev.reply)
  console.log("prod-tune ok [dev-session]")

  const ping = await inbound("ping")
  const pingMeta = ping.meta ?? {}
  if (Number(pingMeta.toolCalls ?? 0) > 0) {
    fail("ping-chat", `expected 0 toolCalls, got ${pingMeta.toolCalls}`)
  }
  if (!String(ping.reply).toLowerCase().includes("pong") && !String(ping.reply).includes("帮")) {
    fail("ping-chat", `unexpected reply: ${String(ping.reply).slice(0, 80)}`)
  }
  console.log("prod-tune ok [ping-chat]")

  const status = await inbound("/状态")
  if (!String(status.reply).includes("当前项目")) fail("/状态", status.reply)
  console.log("prod-tune ok [/状态]")

  const t0 = Date.now()
  const devTask = await inbound(
    "帮我写入 butler-v5/tmp-prod-tune.txt 内容为 prod-tune-ok",
  )
  const elapsed = Date.now() - t0
  const traces = devTask.meta?.traces ?? []
  if (traces.some((t) => String(t).startsWith("write_file@"))) {
    fail("scheme-b", `main loop must not write_file: ${JSON.stringify(traces.slice(-8))}`)
  }
  const delegated =
    traces.some((t) => String(t).startsWith("delegate_to_subagent@")) ||
    String(devTask.reply).includes("子代理")
  if (!delegated) {
    fail("scheme-b", `expected delegate: ${JSON.stringify(traces.slice(-8))}`)
  }
  if (elapsed > 60_000) {
    fail("scheme-b", `inbound too slow: ${elapsed}ms`)
  }
  console.log(`prod-tune ok [scheme-b-delegate] ${elapsed}ms`)

  console.log("prod-tune PASS")
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
