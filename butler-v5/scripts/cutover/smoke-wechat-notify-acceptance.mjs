#!/usr/bin/env node
/**
 * Simulated WeChat acceptance: inbound commands + proactive run-notify outbox.
 *
 * Requires gateway with:
 *   BUTLER_V5_SUBAGENT_ENABLED=1
 *   BUTLER_V5_RUN_NOTIFY_ENABLED=1
 *   BUTLER_V5_TASK_RUN_ASYNC=1
 *   BUTLER_V5_RUN_NOTIFY_MOCK_OUTBOX=/tmp/butler-v5-notify-acceptance.jsonl
 *
 * --audit-only   Skip mock outbox checks; verify subagent/task via audit log only
 *                (use when gateway has real iLink, no mock outbox).
 */
import { readFileSync, rmSync, writeFileSync } from "node:fs"
import { homedir } from "node:os"
import { join } from "node:path"

const auditOnly = process.argv.includes("--audit-only")

const defaultApi = "http://127.0.0.1:3000"
let api = defaultApi
const apiEq = process.argv.find((a) => a.startsWith("--api="))
if (apiEq) api = apiEq.slice("--api=".length)
const base = api.replace(/\/$/, "")

const fromUserId = `notify-accept-${Date.now()}`
const mockOutbox =
  process.env["BUTLER_V5_RUN_NOTIFY_MOCK_OUTBOX"] ??
  "/tmp/butler-v5-notify-acceptance.jsonl"
const auditPath = join(homedir(), ".config", "butler-v5", "audit", "subagent.jsonl")

const SUBAGENT_WAIT_MS = 120_000
const TASK_WAIT_MS = 180_000
const POLL_MS = 3_000

function fail(step, detail) {
  console.error(`acceptance FAIL [${step}]: ${detail}`)
  process.exit(1)
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function inbound(content) {
  const res = await fetch(`${base}/v1/wechat/inbound`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      apiVersion: "v1",
      fromUserId,
      content,
      messageId: `${fromUserId}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      projectId: "wechat",
    }),
  })
  const text = await res.text()
  if (!res.ok) fail("inbound", `${res.status} ${text}`)
  return JSON.parse(text)
}

function readOutbox() {
  try {
    const raw = readFileSync(mockOutbox, "utf8")
    return raw
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => JSON.parse(line))
  } catch {
    return []
  }
}

function readAuditTail(limit = 20) {
  try {
    const raw = readFileSync(auditPath, "utf8")
    const lines = raw
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
    return lines.slice(-limit).map((line) => JSON.parse(line))
  } catch {
    return []
  }
}

async function waitForOutboxMatch(label, predicate, timeoutMs) {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    const rows = readOutbox()
    const hit = rows.find(predicate)
    if (hit) {
      console.log(`acceptance ok [${label}]: ${String(hit.text).slice(0, 80)}`)
      return hit
    }
    await sleep(POLL_MS)
  }
  fail(label, `no mock outbox match within ${timeoutMs}ms (file=${mockOutbox})`)
}

async function waitForSubagentCompletion(taskHint) {
  const start = Date.now()
  while (Date.now() - start < SUBAGENT_WAIT_MS) {
    const rows = readAuditTail(30)
    const done = rows.find(
      (row) => row.kind === "completion" && String(row.task).includes(taskHint),
    )
    if (done) {
      console.log(`acceptance ok [subagent audit completion]: ${String(done.replyExcerpt).slice(0, 60)}`)
      return done
    }
    await sleep(POLL_MS)
  }
  fail("subagent completion", `audit log missing completion for task hint "${taskHint}"`)
}

async function main() {
  if (!(await fetch(`${base}/healthz`)).ok) fail("healthz", "gateway down")
  console.log("acceptance ok [healthz]")

  try {
    rmSync(mockOutbox, { force: true })
  } catch {
    writeFileSync(mockOutbox, "")
  }

  // --- 模拟微信：/委派 ---
  const delegateHint = "notify-accept-delegate"
  const delegate = await inbound(`/委派 只回复 OK（验收 ${delegateHint}），不要调用工具`)
  if (!String(delegate.reply).includes("已委派")) {
    fail("/委派", delegate.reply)
  }
  console.log("acceptance ok [/委派 ack]")
  await waitForSubagentCompletion(delegateHint)
  if (auditOnly) {
    console.log("acceptance ok [subagent notify]: audit-only (skip mock outbox)")
  } else {
    await waitForOutboxMatch(
      "subagent notify",
      (row) => row.to === fromUserId && String(row.text).includes("【子代理"),
      SUBAGENT_WAIT_MS,
    )
  }

  // --- 模拟微信：/待办 + /运行 ---
  const taskTitle = `notify-smoke-${Date.now()}`
  const add = await inbound(`/待办 新增 ${taskTitle} | 只回复 OK，不要调用工具`)
  if (!String(add.reply).includes("已添加待办")) fail("/待办 新增", add.reply)
  const taskToken = String(add.reply).match(/([0-9a-f]{8})/)?.[1]
  if (!taskToken) fail("/待办 新增/token", add.reply)
  console.log(`acceptance ok [/待办 新增]: ${taskToken}`)

  const run = await inbound(`/运行 ${taskToken}`)
  if (!String(run.reply).includes("后台运行")) fail("/运行 async", run.reply)
  console.log("acceptance ok [/运行 async ack]")

  if (auditOnly) {
    console.log(
      "acceptance ok [task notify]: audit-only (async scheduled; push verified via mock outbox or smoke:ilink)",
    )
  } else {
    await waitForOutboxMatch(
      "task notify",
      (row) => row.to === fromUserId && String(row.text).includes("【待办"),
      TASK_WAIT_MS,
    )
  }

  if (!auditOnly) {
    const outbox = readOutbox()
    console.log(`acceptance ok [mock outbox]: ${outbox.length} proactive message(s)`)
  }
  console.log("acceptance PASS")
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
