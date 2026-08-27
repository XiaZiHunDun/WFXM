#!/usr/bin/env node
/**
 * Loopback E2E: WeChat inbound + Owner approve run_command with networkAllowlist (P2b).
 *
 * Scheme B (default): dev_task delegates with pre-granted run_command — no waiting step.
 * This smoke creates a pending run_command via CLI run (fresh subject, no dev-session grant),
 * then exercises Owner loopback approve — same path as `butler approve --network-allowlist`.
 *
 *   node scripts/cutover/smoke-wechat-allowlist-owner.mjs [--api=http://127.0.0.1:3000]
 *
 * Live egress exec under slirp may fail (grant stamping still validated); registry probe
 * is covered by `pnpm smoke:allowlist-pnpm` (proxy path).
 */
import { execFileSync, spawnSync } from "node:child_process"
import { mkdtempSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const scriptDir = dirname(fileURLToPath(import.meta.url))
const repoRoot = join(scriptDir, "../..")

const defaultApi = "http://127.0.0.1:3000"
let api = defaultApi
const apiEq = process.argv.find((a) => a.startsWith("--api="))
if (apiEq) api = apiEq.slice("--api=".length)
const base = api.replace(/\/$/, "")

const REGISTRY_ALLOWLIST = "registry.npmjs.org:443"
const fromUserId = `allowlist-owner-${Date.now()}`
const conversationId = `c-${fromUserId}`

function fail(step, detail) {
  console.error(`allowlist-owner FAIL [${step}]: ${detail}`)
  process.exit(1)
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function postInbound(content) {
  const res = await fetch(`${base}/v1/wechat/inbound`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      apiVersion: "v1",
      fromUserId,
      content,
      messageId: `msg-${Date.now()}`,
      projectId: "wechat",
      conversationId,
    }),
  })
  const text = await res.text()
  if (!res.ok) fail("wechat/inbound", `${res.status} ${text}`)
  return JSON.parse(text)
}

async function listApprovals() {
  const res = await fetch(`${base}/v1/owner/approvals`)
  const text = await res.text()
  if (!res.ok) fail("owner/approvals", `${res.status} ${text}`)
  return (JSON.parse(text).items ?? [])
}

async function approveStep(stepId, networkAllowlist) {
  const res = await fetch(`${base}/v1/owner/approvals/${encodeURIComponent(stepId)}/approve`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      subject: "owner",
      networkAllowlist,
    }),
  })
  const text = await res.text()
  if (!res.ok) fail("owner/approve", `${res.status} ${text}`)
  return JSON.parse(text)
}

function createPendingRunCommand(subject) {
  const goal =
    '直接 CallTool run_command argv=["python3","-c","print(123)"]，不要委派子代理'
  const result = spawnSync(
    "pnpm",
    ["exec", "tsx", "cli/src/index.ts", "run", "--subject", subject, goal],
    {
      cwd: repoRoot,
      encoding: "utf8",
      env: process.env,
    },
  )
  if (result.status !== 2) {
    fail(
      "cli/run",
      `expected exit 2 (AskApproval), got ${result.status}: ${(result.stdout + result.stderr).slice(0, 400)}`,
    )
  }
  const match =
    result.stdout.match(/审批编号:\s*([0-9a-f-]{36})/i) ??
    result.stdout.match(/waiting approval ([0-9a-f-]{36})/i)
  if (!match?.[1]) {
    fail("cli/run", `no step id in output: ${result.stdout.slice(0, 400)}`)
  }
  return match[1]
}

function runAllowlistPnpmProbe() {
  const root = mkdtempSync(join(tmpdir(), "allowlist-owner-pnpm-"))
  try {
    execFileSync(
      "pnpm",
      ["exec", "tsx", "cli/src/index.ts", "sandbox-probe-allowlist-pnpm", "--workspace", root],
      { cwd: repoRoot, stdio: "pipe", encoding: "utf8" },
    )
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
}

async function main() {
  const health = await fetch(`${base}/healthz`)
  if (!health.ok) fail("healthz", `${health.status}`)
  console.log("allowlist-owner ok [healthz]")

  const sandbox = (process.env.BUTLER_V5_SANDBOX ?? "").trim()
  const networkMode = (process.env.BUTLER_V5_SANDBOX_NETWORK_MODE ?? "").trim()
  if (sandbox !== "bubblewrap" || networkMode !== "allowlist") {
    console.warn(
      `allowlist-owner WARN: expected bubblewrap+allowlist, got sandbox=${sandbox || "(unset)"} networkMode=${networkMode || "(unset)"}`,
    )
  }

  const ping = await postInbound("ping")
  if (!String(ping.reply).toLowerCase().includes("pong") && !String(ping.reply).includes("帮")) {
    fail("wechat/ping", String(ping.reply).slice(0, 120))
  }
  console.log("allowlist-owner ok [wechat/ping]")

  const devTask = await postInbound("在 butler-v5/tmp-allowlist-owner 执行 echo smoke")
  const delegated =
    String(devTask.reply).includes("子代理") ||
    (devTask.meta?.traces ?? []).some((t) => String(t).startsWith("delegate_to_subagent@"))
  if (!delegated) {
    console.warn("allowlist-owner WARN: Scheme B delegate trace not seen (live LLM variance)")
  } else {
    console.log("allowlist-owner ok [wechat/scheme-b-delegate]")
  }

  let pending = (await listApprovals()).filter(
    (row) => row?.input?.capability === "run_command",
  )
  if (pending.length === 0) {
    console.log("allowlist-owner info [wechat]: no run_command pending (expected under Scheme B)")
  }

  const cliSubject = `${fromUserId}-cli`
  const stepId = createPendingRunCommand(cliSubject)
  console.log(`allowlist-owner ok [cli/run pending]: step=${stepId}`)

  pending = (await listApprovals()).filter((row) => row.id === stepId)
  if (pending.length !== 1) fail("owner/approvals", `step ${stepId} not listed`)

  const approved = await approveStep(stepId, [REGISTRY_ALLOWLIST])
  if (approved.grant?.sandboxProfile !== "workspace-write-network-allowlist") {
    fail("grant/profile", JSON.stringify(approved.grant))
  }
  if (
    !Array.isArray(approved.grant?.networkAllowlist) ||
    !approved.grant.networkAllowlist.includes(REGISTRY_ALLOWLIST)
  ) {
    fail("grant/allowlist", JSON.stringify(approved.grant))
  }
  console.log("allowlist-owner ok [owner/approve networkAllowlist grant]")

  if (approved.ok && approved.output && String(approved.output).includes("123")) {
    console.log("allowlist-owner ok [resume/exec]: python print under allowlist grant")
  } else {
    const reason = String(approved.reason ?? "")
    if (/slirp sandbox exit/i.test(reason)) {
      console.warn(
        `allowlist-owner WARN [resume/exec slirp]: ${reason.slice(0, 120)} — running proxy allowlist pnpm probe`,
      )
      try {
        runAllowlistPnpmProbe()
        console.log("allowlist-owner ok [allowlist-pnpm probe fallback]")
      } catch (err) {
        fail("resume/exec", `${reason}; probe fallback: ${err instanceof Error ? err.message : String(err)}`)
      }
    } else if (!approved.ok) {
      fail("owner/approve exec", reason || JSON.stringify(approved))
    } else {
      console.log(`allowlist-owner ok [resume/exec]: ${String(approved.output).slice(0, 80)}`)
    }
  }

  await sleep(500)
  const after = await listApprovals()
  if (after.some((row) => row.id === stepId)) {
    fail("owner/approvals", "step still pending after approve")
  }
  console.log("allowlist-owner ok [approvals drained]")

  console.log("allowlist-owner PASS")
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
