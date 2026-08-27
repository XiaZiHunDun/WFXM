#!/usr/bin/env node
/**
 * L2 aggregated loopback regression — no real WeChat device required.
 *
 *   node scripts/cutover/smoke-regression.mjs [--quick] [--api=URL] [--skip=NAME]
 *
 * --quick   Skip LLM-heavy project-knowledge and full MCP grant path
 * --skip=X  Skip step named X (commands|surface|productivity|notify|pk|mcp|memory|ingest)
 */
import { spawnSync } from "node:child_process"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const scriptDir = dirname(fileURLToPath(import.meta.url))
const repoRoot = join(scriptDir, "../..")

const args = process.argv.slice(2)
const quick = args.includes("--quick")
const skip = new Set(
  args.filter((a) => a.startsWith("--skip=")).map((a) => a.slice("--skip=".length)),
)
const apiEq = args.find((a) => a.startsWith("--api="))
const apiFlag = apiEq ? [`--api=${apiEq.slice("--api=".length)}`] : []

function fail(step, detail) {
  console.error(`regression FAIL [${step}]: ${detail}`)
  process.exit(1)
}

function runStep(name, script, extraArgs = []) {
  if (skip.has(name)) {
    console.log(`regression SKIP [${name}]`)
    return
  }
  const ciSkipNotify = process.env["BUTLER_V5_CI_SMOKE"] === "1" && name === "notify"
  if (ciSkipNotify) {
    console.log(`regression SKIP [${name}] (BUTLER_V5_CI_SMOKE)`)
    return
  }
  const path = join(scriptDir, script)
  console.log(`\n=== regression [${name}] ${script} ===`)
  const result = spawnSync(process.execPath, [path, ...apiFlag, ...extraArgs], {
    cwd: repoRoot,
    stdio: "inherit",
    env: process.env,
  })
  if (result.status !== 0) {
    fail(name, `exit ${result.status ?? "signal"}`)
  }
  console.log(`regression ok [${name}]`)
}

async function l0() {
  console.log("\n=== regression [L0 verify] ===")
  const verify = spawnSync(
    "pnpm",
    ["exec", "tsx", "cli/src/index.ts", "verify", ...(apiEq ? ["--api", apiEq.slice("--api=".length)] : [])],
    { cwd: repoRoot, stdio: "inherit", env: process.env },
  )
  if (verify.status !== 0) fail("L0/verify", `exit ${verify.status}`)
  console.log("regression ok [L0/verify]")
}

async function main() {
  console.log(`regression start quick=${quick}`)
  await l0()

  runStep("commands", "smoke-wechat-inbound-commands.mjs")
  runStep("surface", "smoke-wechat-project-surface.mjs")
  runStep("product-contract", "smoke-wechat-product-contract.mjs")
  runStep("productivity", "smoke-wechat-productivity.mjs")
  runStep("notify", "smoke-wechat-notify-acceptance.mjs", ["--audit-only"])

  if (!quick) {
    runStep("pk", "smoke-project-knowledge.mjs")
    runStep("mcp", "smoke-mcp-hardened.mjs")
  } else {
    runStep("mcp", "smoke-mcp-hardened.mjs", ["--skip-grant"])
  }

  runStep("memory", "smoke-durable-memory.mjs")
  runStep("ingest", "smoke-document-ingest.mjs")

  console.log("\nregression PASS (loopback L2 — real device not required)")
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
