#!/usr/bin/env node
/**
 * T3: Scheme B product contract smoke (loopback, asserts traces not LLM prose).
 *
 * Requires gateway with:
 *   BUTLER_V5_LLM_FIXTURE_DIR=config/llm-fixtures/wechat
 *   BUTLER_V5_SUBAGENT_ENABLED=1
 *   BUTLER_V5_RUN_NOTIFY_MOCK_OUTBOX=/tmp/butler-v5-product-contract.jsonl
 */
import { readFileSync, rmSync, writeFileSync, existsSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const scriptDir = dirname(fileURLToPath(import.meta.url))
const repoRoot = join(scriptDir, "../..")
const defaultApi = "http://127.0.0.1:3000"
let api = defaultApi
const apiEq = process.argv.find((a) => a.startsWith("--api="))
if (apiEq) api = apiEq.slice("--api=".length)
const base = api.replace(/\/$/, "")
const fromUserId =
  (process.env.BUTLER_OWNER_WECHAT_ID ?? "").trim() || `product-contract-${Date.now()}`
const conversationId = `c-wechat-product-contract-${Date.now()}`
const mockOutbox =
  process.env.BUTLER_V5_RUN_NOTIFY_MOCK_OUTBOX ??
  "/tmp/butler-v5-ci-notify.jsonl"
const fixtureDir =
  process.env.BUTLER_V5_LLM_FIXTURE_DIR ??
  join(repoRoot, "config/llm-fixtures/wechat")

function fail(step, detail) {
  console.error(`product-contract FAIL [${step}]: ${detail}`)
  process.exit(1)
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function readOutbox() {
  if (!existsSync(mockOutbox)) return []
  return readFileSync(mockOutbox, "utf8")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
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

async function pollOutbox(includes, timeoutMs = 120_000) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const lines = readOutbox()
    if (lines.some((line) => line.includes(includes))) return lines
    await sleep(500)
  }
  fail("async-outbox", `timeout waiting for "${includes}" in ${mockOutbox}`)
}

async function main() {
  if (!process.env.BUTLER_V5_LLM_FIXTURE_DIR) {
    console.warn(
      "product-contract WARN: BUTLER_V5_LLM_FIXTURE_DIR unset — gateway should use live LLM (T4); CI expects fixture mode",
    )
  }

  try {
    rmSync(mockOutbox, { force: true })
  } catch {
    // ignore
  }
  writeFileSync(mockOutbox, "")

  if (!(await fetch(`${base}/healthz`)).ok) fail("healthz", "down")
  console.log("product-contract ok [healthz]")

  await inbound("开发模式")
  console.log("product-contract ok [dev-session]")

  const ping = await inbound("ping")
  if (Number(ping.meta?.toolCalls ?? 0) > 0) {
    fail("ping", `expected 0 toolCalls got ${ping.meta.toolCalls}`)
  }
  console.log("product-contract ok [ping]")

  const dev = await inbound("帮我写入 butler-v5/tmp-product-contract.txt 内容 contract-ok")
  const traces = dev.meta?.traces ?? []
  if (traces.some((t) => String(t).startsWith("write_file@"))) {
    fail("scheme-b", `main loop must not write_file: ${JSON.stringify(traces)}`)
  }
  const delegated =
    traces.some((t) => String(t).startsWith("delegate_to_subagent@")) ||
    String(dev.reply).includes("子代理")
  if (!delegated) {
    fail("scheme-b", `expected delegate trace or reply: ${JSON.stringify(traces.slice(-8))}`)
  }
  console.log("product-contract ok [scheme-b-delegate]")

  const outboxLines = await pollOutbox("【开发验收】")
  console.log(`product-contract ok [async-verify-outbox] lines=${outboxLines.length}`)

  console.log(`product-contract PASS (fixtureDir=${fixtureDir})`)
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
