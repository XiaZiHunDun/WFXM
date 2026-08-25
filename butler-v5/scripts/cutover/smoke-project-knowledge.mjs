#!/usr/bin/env node
/**
 * Smoke: WeChat loop Project Knowledge inject + recall (loopback).
 * Requires gateway with BUTLER_V5_PROJECT_KNOWLEDGE=1 and seeded PK for projectId WFXM.
 *
 *   node scripts/cutover/smoke-project-knowledge.mjs [--api=http://127.0.0.1:3000]
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
const projectId = "WFXM"
const fromUserId = `pk-smoke-${Date.now()}`

function fail(step, detail) {
  console.error(`smoke FAIL [${step}]: ${detail}`)
  process.exit(1)
}

async function postInbound(content, messageId, inboundProjectId = projectId) {
  const res = await fetch(`${base}/v1/wechat/inbound`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      apiVersion: "v1",
      fromUserId,
      content,
      messageId,
      projectId: inboundProjectId,
      conversationId: `c-${inboundProjectId}-${fromUserId}`,
    }),
  })
  const text = await res.text()
  if (!res.ok) fail("wechat/inbound", `${res.status} ${text}`)
  return JSON.parse(text)
}

function assertInjectTraces(meta, step) {
  const traces = meta?.traces ?? []
  if (!traces.some((t) => t.includes("project-knowledge: injected working-set prefix"))) {
    fail(step, `missing PK inject trace in ${JSON.stringify(traces)}`)
  }
}

async function main() {
  const health = await fetch(`${base}/healthz`)
  if (!health.ok) fail("healthz", `${health.status}`)
  console.log("smoke ok [healthz]")

  const pkList = await fetch(`${base}/v1/owner/project-knowledge?projectId=${encodeURIComponent(projectId)}`)
  const pkText = await pkList.text()
  if (!pkList.ok) fail("project-knowledge/list", `${pkList.status} ${pkText}`)
  const pkBody = JSON.parse(pkText)
  const itemCount = (pkBody.items ?? []).length
  if (itemCount < 1) {
    fail("project-knowledge/list", `expected seeded PK for ${projectId}, got ${pkText}`)
  }
  console.log(`smoke ok [project-knowledge/list]: ${itemCount} items for ${projectId}`)

  // Inject path: proposal doc should be in working-set prefix → 0 toolCalls ideal
  const injectQ =
    "WFXM 里 Project Knowledge 立项文档的状态是什么？只回答 Accepted、Draft 或 Pending 之一。"
  const injectRes = await postInbound(injectQ, `pk-smoke-inject-${Date.now()}`)
  assertInjectTraces(injectRes.meta, "inject/traces")
  const reply = String(injectRes.reply ?? "")
  if (!/accepted/i.test(reply)) {
    fail("inject/reply", `expected Accepted in reply, got: ${reply.slice(0, 400)}`)
  }
  console.log(
    `smoke ok [inject]: toolCalls=${injectRes.meta?.toolCalls ?? "?"} reply mentions Accepted`,
  )

  // Recall path: distinctive manual note about MCP tool count
  const recallQ =
    "生产 MCP 一共接了多少个 tools？只回答数字；若不确定请先用 recall_project_knowledge 查 WFXM 项目知识。"
  const recallRes = await postInbound(recallQ, `pk-smoke-recall-${Date.now()}`)
  assertInjectTraces(recallRes.meta, "recall/traces")
  const recallReply = String(recallRes.reply ?? "")
  const toolCalls = recallRes.meta?.toolCalls ?? 0
  const traces = recallRes.meta?.traces ?? []
  const usedRecallTool = traces.some((t) => t.startsWith("recall_project_knowledge@"))
  if (!usedRecallTool && !/\b22\b/.test(recallReply)) {
    fail(
      "recall/reply",
      `expected 22 or recall_project_knowledge tool; toolCalls=${toolCalls} traces=${JSON.stringify(traces)} reply=${recallReply.slice(0, 400)}`,
    )
  }
  console.log(
    `smoke ok [recall]: toolCalls=${toolCalls} recallTool=${usedRecallTool} reply=${recallReply.slice(0, 120)}`,
  )

  // Real ilink path uses projectId=wechat; PK store is WFXM (default inbound map)
  const wechatInjectQ =
    "WFXM Project Knowledge 立项状态？只回答 Accepted、Draft 或 Pending 之一。"
  const wechatRes = await postInbound(wechatInjectQ, `pk-smoke-wechat-${Date.now()}`, "wechat")
  assertInjectTraces(wechatRes.meta, "wechat/inject/traces")
  const wechatReply = String(wechatRes.reply ?? "")
  if (!/accepted/i.test(wechatReply)) {
    fail("wechat/inject/reply", `expected Accepted via wechat→WFXM map, got: ${wechatReply.slice(0, 400)}`)
  }
  console.log(`smoke ok [wechat→WFXM inject]: toolCalls=${wechatRes.meta?.toolCalls ?? "?"}`)

  // LingWen1 inbound map → LingWen PK (requires BUTLER_V5_PROJECT_KNOWLEDGE_INBOUND_MAP)
  const lwList = await fetch(
    `${base}/v1/owner/project-knowledge?projectId=${encodeURIComponent("LingWen")}`,
  )
  const lwText = await lwList.text()
  if (!lwList.ok) fail("project-knowledge/LingWen", `${lwList.status} ${lwText}`)
  const lwBody = JSON.parse(lwText)
  const lwCount = (lwBody.items ?? []).length
  if (lwCount < 5) {
    fail("project-knowledge/LingWen", `expected >=5 LingWen items, got ${lwCount}`)
  }
  console.log(`smoke ok [project-knowledge/LingWen]: ${lwCount} items`)

  const lwQ =
    "灵文1号当前默认是维护态还是新书态？只回答「维护态」或「新书态」之一；可参考项目知识 dual-playbook。"
  const lwRes = await postInbound(lwQ, `pk-smoke-lingwen-${Date.now()}`, "LingWen1")
  assertInjectTraces(lwRes.meta, "LingWen1/inject/traces")
  const lwReply = String(lwRes.reply ?? "")
  if (!/维护态/.test(lwReply)) {
    fail("LingWen1/inject/reply", `expected 维护态 via LingWen1→LingWen map, got: ${lwReply.slice(0, 400)}`)
  }
  console.log(`smoke ok [LingWen1→LingWen inject]: toolCalls=${lwRes.meta?.toolCalls ?? "?"}`)

  console.log("smoke PASS")
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
