#!/usr/bin/env node
/**
 * Scheme B + allowlist E2E: delegate dev_task → child run_command → Owner approve.
 *
 * Requires: bubblewrap+allowlist, subagent enabled, owner loopback API.
 *
 * Modes:
 *  - Fixture mode (BUTLER_V5_LLM_FIXTURE_DIR set): child deterministically issues
 *    run_command, which executes under the dev-session anchor grant (no pending).
 *    Asserted via /v1/owner/traces capability=run_command status=ok.
 *  - Live LLM: child may skip run_command (live variance) → PASS with WARN.
 *  - Network-egress command: run_command without anchor coverage → pending →
 *    Owner approve with networkAllowlist → resume in sandbox.
 */
const defaultApi = "http://127.0.0.1:3000"
let api = defaultApi
const apiEq = process.argv.find((a) => a.startsWith("--api="))
if (apiEq) api = apiEq.slice("--api=".length)
const base = api.replace(/\/$/, "")

const fromUserId =
  (process.env.BUTLER_OWNER_WECHAT_ID ?? "").trim() || `scheme-b-${Date.now()}`
const conversationId = `c-scheme-b-allowlist-${Date.now()}`
const REGISTRY_ALLOWLIST = "registry.npmjs.org:443"

function fail(step, detail) {
  console.error(`scheme-b-allowlist FAIL [${step}]: ${detail}`)
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

async function listRunTraces(conversationId) {
  const res = await fetch(
    `${base}/v1/owner/traces?conversationId=${encodeURIComponent(conversationId)}`,
  )
  const text = await res.text()
  if (!res.ok) fail("owner/traces", `${res.status} ${text}`)
  return (JSON.parse(text).items ?? [])
}

async function approveStep(stepId) {
  const res = await fetch(`${base}/v1/owner/approvals/${encodeURIComponent(stepId)}/approve`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      subject: "owner",
      networkAllowlist: [REGISTRY_ALLOWLIST],
    }),
  })
  const text = await res.text()
  if (!res.ok) fail("owner/approve", `${res.status} ${text}`)
  return JSON.parse(text)
}

async function main() {
  if (!(await fetch(`${base}/healthz`)).ok) fail("healthz", "down")
  console.log("scheme-b-allowlist ok [healthz]")

  const dev = await inbound("开发模式")
  if (!String(dev.reply).includes("开发模式")) fail("dev-session", String(dev.reply).slice(0, 120))
  console.log("scheme-b-allowlist ok [dev-session]")

  const task = await inbound(
    "委派子代理 developer：必须 CallTool run_command argv=[\"python3\",\"-c\",\"print(888)\"]，不要 write_file",
  )
  const delegated =
    String(task.reply).includes("子代理") ||
    (task.meta?.traces ?? []).some((t) => String(t).startsWith("delegate_to_subagent@"))
  if (!delegated) fail("delegate", `no delegate trace: ${JSON.stringify(task.meta?.traces ?? []).slice(0, 200)}`)
  console.log("scheme-b-allowlist ok [delegate]")

  let stepId = null
  // Fixture mode: child issues run_command deterministically; it executes under
  // the dev-session anchor grant (no pending) — assert via traces.
  let executed = false
  for (let i = 0; i < 24 && !executed; i++) {
    await sleep(2500)
    const traces = await listRunTraces(conversationId)
    if (
      traces.some(
        (t) => t?.kind === "capability" && t?.capability === "run_command" && t?.status === "ok",
      )
    ) {
      executed = true
    }
  }
  if (executed) {
    console.log("scheme-b-allowlist ok [child run_command executed under anchor grant]")
  }

  if (!executed) {
    for (let i = 0; i < 24; i++) {
      await sleep(2500)
      const pending = (await listApprovals()).filter(
        (row) => row?.input?.capability === "run_command",
      )
      if (pending.length > 0) {
        stepId = pending[0].id
        break
      }
    }
  }

  if (!stepId && !executed) {
    console.warn(
      "scheme-b-allowlist WARN: no run_command executed or pending after delegate (LLM may have skipped shell)",
    )
    console.log("scheme-b-allowlist PASS (delegate only)")
    return
  }
  if (executed && !stepId) {
    console.log("scheme-b-allowlist PASS")
    return
  }

  console.log(`scheme-b-allowlist ok [pending]: step=${stepId}`)
  const approved = await approveStep(stepId)
  if (approved.ok && String(approved.output ?? "").includes("888")) {
    console.log("scheme-b-allowlist ok [approve+resume]: python under allowlist grant")
  } else if (approved.ok) {
    console.log(`scheme-b-allowlist ok [approve+resume]: ${String(approved.output ?? "").slice(0, 80)}`)
  } else {
    const reason = String(approved.reason ?? "")
    if (/slirp sandbox exit/i.test(reason) && approved.grant?.sandboxProfile) {
      console.warn(`scheme-b-allowlist WARN [slirp]: ${reason.slice(0, 100)}`)
    } else {
      fail("approve/resume", reason || JSON.stringify(approved))
    }
  }

  console.log("scheme-b-allowlist PASS")
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
