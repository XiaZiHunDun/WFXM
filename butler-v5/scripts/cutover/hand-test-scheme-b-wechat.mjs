#!/usr/bin/env node
/**
 * 真机手测（loopback 模拟微信）：开发模式 → 委派 → run_command pending → Owner approve。
 * 使用 BUTLER_OWNER_WECHAT_ID，与 iLink 入站同路径。
 */
const base = (process.argv.find((a) => a.startsWith("--api="))?.slice(7) ?? "http://127.0.0.1:3000").replace(/\/$/, "")
const fromUserId = (process.env.BUTLER_OWNER_WECHAT_ID ?? "").trim()
if (!fromUserId) {
  console.error("hand-test FAIL: BUTLER_OWNER_WECHAT_ID unset")
  process.exit(1)
}
const conversationId = `c-hand-test-${Date.now()}`
const REGISTRY = "registry.npmjs.org:443"

function log(tag, msg) {
  console.log(`hand-test ${tag} ${msg}`)
}

function fail(step, detail) {
  console.error(`hand-test FAIL [${step}]: ${detail}`)
  process.exit(1)
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function inbound(content) {
  const res = await fetch(`${base}/v1/wechat/inbound`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      apiVersion: "v1",
      fromUserId,
      content,
      messageId: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      projectId: "wechat",
      conversationId,
    }),
  })
  const text = await res.text()
  if (!res.ok) fail("inbound", `${res.status} ${text}`)
  const body = JSON.parse(text)
  log("inbound", `«${content.slice(0, 40)}…» → ${String(body.reply).slice(0, 120).replace(/\n/g, " ")}`)
  return body
}

async function listApprovals() {
  const res = await fetch(`${base}/v1/owner/approvals`)
  if (!res.ok) fail("approvals", `${res.status}`)
  return (JSON.parse(await res.text()).items ?? [])
}

async function approve(stepId) {
  const res = await fetch(`${base}/v1/owner/approvals/${encodeURIComponent(stepId)}/approve`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ subject: "owner", networkAllowlist: [REGISTRY] }),
  })
  const text = await res.text()
  if (!res.ok) fail("approve", `${res.status} ${text}`)
  return JSON.parse(text)
}

async function main() {
  if (!(await fetch(`${base}/healthz`)).ok) fail("healthz", "down")
  log("ok", `[healthz] owner=${fromUserId.slice(0, 12)}… conv=${conversationId}`)

  const dev = await inbound("开发模式")
  if (!String(dev.reply).includes("开发模式")) fail("dev-session", dev.reply)

  const task = await inbound(
    [
      "请委派子代理 developer 完成以下任务（禁止主循环直接 write_file/run_command）：",
      "执行 shell：python3 -c \"print(888)\"",
      "子代理必须调用 run_command，不要用 write_file。",
    ].join("\n"),
  )
  const traces = task.meta?.traces ?? []
  if (!traces.some((t) => String(t).startsWith("delegate_to_subagent@"))) {
    fail("delegate", `no delegate: ${JSON.stringify(traces.slice(-6))}`)
  }
  log("ok", "[delegate] waiting for subagent worker…")

  let stepId = null
  let lastPending = []
  for (let i = 0; i < 36; i++) {
    await sleep(2500)
    lastPending = (await listApprovals()).filter((r) => r?.input?.capability === "run_command")
    if (lastPending.length > 0) {
      stepId = lastPending[0].id
      log("ok", `[pending] step=${stepId} run=${lastPending[0].runId ?? "?"}`)
      break
    }
    if (i % 4 === 3) log("info", `[poll] still waiting (${(i + 1) * 2.5}s)…`)
  }

  if (!stepId) {
    log("warn", "no run_command pending — trying follow-up nudge")
    await inbound("子代理请立即 run_command：python3 -c \"print(888)\"")
    for (let i = 0; i < 12; i++) {
      await sleep(2500)
      lastPending = (await listApprovals()).filter((r) => r?.input?.capability === "run_command")
      if (lastPending.length > 0) {
        stepId = lastPending[0].id
        break
      }
    }
  }

  if (!stepId) {
    fail("pending", `no run_command approval after 90s+; approvals=${lastPending.length}`)
  }

  const approved = await approve(stepId)
  log("ok", `[grant] profile=${approved.grant?.sandboxProfile} allowlist=${JSON.stringify(approved.grant?.networkAllowlist)}`)
  if (!approved.ok) fail("resume", approved.reason ?? JSON.stringify(approved))

  const out = String(approved.output ?? "")
  if (out.includes("888")) {
    log("ok", "[resume/exec] python print(888) SUCCESS")
  } else {
    log("ok", `[resume/exec] output=${out.slice(0, 100)}`)
  }

  const after = await listApprovals()
  if (after.some((r) => r.id === stepId)) fail("drain", "step still pending")
  log("PASS", "Scheme B 真机手测完成")
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
