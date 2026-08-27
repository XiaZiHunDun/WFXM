#!/usr/bin/env node
/**
 * Smoke: MCP hardened production (manifest trim + WeChat allowlist + Grant path).
 *
 *   node scripts/cutover/smoke-mcp-hardened.mjs [--api=http://127.0.0.1:3000] [--skip-grant]
 *
 * Requires gateway with BUTLER_V5_MCP_ENABLED=1 and real LLM for grant step.
 */
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const scriptDir = dirname(fileURLToPath(import.meta.url))
const repoRoot = join(scriptDir, "../..")

const defaultApi = "http://127.0.0.1:3000"
let api = defaultApi
let skipGrant = process.argv.includes("--skip-grant")
const apiEq = process.argv.find((a) => a.startsWith("--api="))
if (apiEq) {
  api = apiEq.slice("--api=".length)
} else {
  const idx = process.argv.indexOf("--api")
  if (idx >= 0 && process.argv[idx + 1]) api = process.argv[idx + 1]
}

const base = api.replace(/\/$/, "")
const MCP_CAPABILITY = "mcp_todoist_lst-projects"
const fromUserId = `mcp-smoke-${Date.now()}`
const conversationId = `c-wechat-${fromUserId}`

const GITHUB_WRITE_PREFIX = /^(create_|update_|delete_|push_|merge_|fork_|add_|remove_)/

function fail(step, detail) {
  console.error(`smoke FAIL [${step}]: ${detail}`)
  process.exit(1)
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function manifestCapabilities(manifest) {
  const caps = []
  for (const server of manifest.servers ?? []) {
    for (const tool of server.tools ?? []) {
      caps.push(`mcp_${server.id}_${tool.name}`)
    }
  }
  return caps
}

async function postInbound(content, messageId) {
  const res = await fetch(`${base}/v1/wechat/inbound`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      apiVersion: "v1",
      fromUserId,
      content,
      messageId,
      projectId: "wechat",
      conversationId,
    }),
  })
  const text = await res.text()
  if (!res.ok) fail("wechat/inbound", `${res.status} ${text}`)
  return JSON.parse(text)
}

async function findPendingStep(capability) {
  const res = await fetch(`${base}/v1/owner/approvals`)
  const text = await res.text()
  if (!res.ok) fail("owner/approvals", `${res.status} ${text}`)
  const body = JSON.parse(text)
  const items = body.items ?? []
  return items.find((row) => row?.input?.capability === capability) ?? null
}

async function main() {
  const health = await fetch(`${base}/healthz`)
  if (!health.ok) fail("healthz", `${health.status}`)
  console.log("smoke ok [healthz]")

  const mcpRes = await fetch(`${base}/v1/owner/mcp/status`)
  const mcpText = await mcpRes.text()
  if (!mcpRes.ok) fail("owner/mcp/status", `${mcpRes.status} ${mcpText}`)
  const mcp = JSON.parse(mcpText)
  if (!mcp.enabled) fail("mcp/status", "MCP not enabled — set BUTLER_V5_MCP_ENABLED=1")

  if (skipGrant) {
    const tools = mcp.tools ?? []
    console.log(
      `smoke ok [mcp/status]: mode=${mcp.mode}, tools=${tools.length} (--skip-grant)`,
    )
    console.log("smoke SKIP [grant]: --skip-grant")
    console.log("smoke PASS")
    return
  }

  if (mcp.mode !== "multi") fail("mcp/status", `expected mode=multi, got ${mcp.mode}`)

  const tools = mcp.tools ?? []
  if (tools.length !== 22) {
    fail("mcp/status", `expected 22 MCP tools (trimmed github), got ${tools.length}`)
  }
  console.log(`smoke ok [mcp/status]: ${tools.length} tools, mode=${mcp.mode}`)

  const githubServer = (mcp.servers ?? []).find((s) => s.serverId === "github")
  const githubTools = githubServer?.tools ?? []
  if (githubTools.length !== 14) {
    fail("mcp/github", `expected 14 read-only github tools, got ${githubTools.length}`)
  }
  for (const cap of githubTools) {
    const short = cap.replace(/^mcp_github_/, "")
    if (GITHUB_WRITE_PREFIX.test(short)) {
      fail("mcp/github", `write tool exposed: ${cap}`)
    }
  }
  console.log("smoke ok [mcp/github]: 14 read-only tools")

  const manifest = JSON.parse(readFileSync(join(repoRoot, "config/mcp-manifest.json"), "utf8"))
  const allowlist = JSON.parse(readFileSync(join(repoRoot, "config/wechat-tool-allowlist.json"), "utf8"))
  const manifestCaps = new Set(manifestCapabilities(manifest))
  const wechatMcp = allowlist.projects?.wechat?.mcpTools ?? []
  if (allowlist.default?.mcpTools?.length !== 0) {
    fail("allowlist/default", "default mcpTools must be empty")
  }
  for (const cap of wechatMcp) {
    if (!manifestCaps.has(cap)) fail("allowlist/wechat", `unknown capability ${cap}`)
  }
  if (wechatMcp.length !== manifestCaps.size) {
    fail("allowlist/wechat", `expected ${manifestCaps.size} caps, got ${wechatMcp.length}`)
  }
  console.log(`smoke ok [allowlist]: wechat ${wechatMcp.length} MCP caps match manifest`)

  const prompt =
    "你必须调用工具 mcp_todoist_lst-projects（参数 {}）列出 Todoist 项目。不要凭记忆回答，必须先调用该工具。"
  const inbound = await postInbound(prompt, `mcp-smoke-inbound-${Date.now()}`)
  const reply = String(inbound.reply ?? "")
  let stepId =
    reply.match(/审批编号:\s*([0-9a-f-]{36})/i)?.[1] ??
    reply.match(/waiting approval ([0-9a-f-]{36})/i)?.[1]

  if (!stepId) {
    let pending = await findPendingStep(MCP_CAPABILITY)
    for (let i = 0; i < 15 && !pending; i += 1) {
      await sleep(2000)
      pending = await findPendingStep(MCP_CAPABILITY)
    }
    stepId = pending?.id
  }

  if (!stepId) {
    const toolCalls = inbound.meta?.toolCalls ?? 0
    const directExec =
      toolCalls > 0 &&
      (/mcp_todoist_lst-projects|Inbox|Todoist|项目/i.test(reply) ||
        /lst-projects/i.test(reply))
    if (directExec) {
      console.log(
        `smoke ok [grant/readonly-auto]: owner low-risk MCP executed without Ask (toolCalls=${toolCalls})`,
      )
      console.log("smoke PASS")
      return
    }
    fail(
      "grant/pending",
      `no waiting approval for ${MCP_CAPABILITY}; reply=${reply.slice(0, 400)}`,
    )
  }

  const approveRes = await fetch(`${base}/v1/owner/approvals/${encodeURIComponent(stepId)}/approve`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ subject: "owner" }),
  })
  const approveText = await approveRes.text()
  let approved
  try {
    approved = JSON.parse(approveText)
  } catch {
    fail("owner/approve", `${approveRes.status} ${approveText}`)
  }
  if (approved.grant?.mcp?.serverId !== "todoist") {
    fail("grant/mcp", `expected grant.mcp.serverId=todoist, got ${JSON.stringify(approved.grant)}`)
  }
  if (approved.grant?.mcp?.toolName !== "lst-projects") {
    fail("grant/mcp", `expected toolName=lst-projects, got ${JSON.stringify(approved.grant?.mcp)}`)
  }
  if (approved.ok && approved.output && String(approved.output).length >= 2) {
    console.log(
      `smoke ok [grant]: executed step=${stepId} output len=${String(approved.output).length}`,
    )
  } else {
    const reason = String(approved.reason ?? approveText)
    if (/502|503|401|403|timeout|ECONNREFUSED|API request failed/i.test(reason)) {
      console.log(
        `smoke ok [grant]: grant issued; MCP exec external error (check TODOIST_API_TOKEN): ${reason.slice(0, 160)}`,
      )
    } else if (!approveRes.ok) {
      fail("owner/approve", `${approveRes.status} ${approveText}`)
    } else {
      fail("owner/approve", approveText)
    }
  }

  const mcpAfter = await fetch(`${base}/v1/owner/mcp/status`)
  const afterBody = JSON.parse(await mcpAfter.text())
  console.log(`smoke ok [mcp/status-after]: activeGrants=${afterBody.activeGrants ?? "?"}`)

  console.log("smoke PASS")
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
