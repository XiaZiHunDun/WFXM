#!/usr/bin/env node
/**
 * Production point-check: gateway + sandbox binary + allowlist egress (P2c).
 * Optional: --pnpm live registry probe (needs network).
 */
import { execFileSync } from "node:child_process"
import { mkdtempSync, writeFileSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { fileURLToPath } from "node:url"
import { dirname, join } from "node:path"

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "../..")
const defaultApi = "http://127.0.0.1:3000"
const envFile = process.env.HOME
  ? `${process.env.HOME}/.config/butler-v5/env`
  : "/home/ailearn/.config/butler-v5/env"
const livePnpm = process.argv.includes("--pnpm")
const liveSlirp = process.argv.includes("--slirp")

function fail(step, detail) {
  console.error(`smoke FAIL [${step}]: ${detail}`)
  process.exit(1)
}

function readEnvHint() {
  try {
    const text = execFileSync(
      "grep",
      ["-E", "BUTLER_V5_SANDBOX|BUTLER_V5_SANDBOX_NETWORK_MODE|BUTLER_V5_DURABLE", envFile],
      { encoding: "utf8" },
    )
    return text.trim()
  } catch {
    return "(env file not readable)"
  }
}

function runCli(subcommand, extraArgs = []) {
  execFileSync("pnpm", ["exec", "tsx", "cli/src/index.ts", subcommand, ...extraArgs], {
    stdio: "inherit",
    cwd: repoRoot,
  })
}

async function main() {
  const health = await fetch(`${defaultApi}/healthz`)
  if (!health.ok) fail("healthz", `${health.status}`)
  console.log("smoke ok [healthz]")

  const envHint = readEnvHint()
  console.log(`smoke info [env]: ${envHint.replace(/\n/g, " | ")}`)
  if (!envHint.includes("BUTLER_V5_SANDBOX=bubblewrap")) {
    console.error("smoke WARN: bubblewrap not set in operator env")
  }
  if (!envHint.includes("BUTLER_V5_SANDBOX_NETWORK_MODE=allowlist")) {
    console.error("smoke WARN: SANDBOX_NETWORK_MODE=allowlist not in operator env")
  }

  runCli("sandbox-probe")
  console.log("smoke ok [sandbox-network]")

  runCli("sandbox-probe-allowlist")
  console.log("smoke ok [sandbox-allowlist]")

  runCli("sandbox-p2d-preflight")
  console.log("smoke ok [p2d-preflight]")

  if (liveSlirp) {
    runCli("sandbox-probe-allowlist-slirp", [
      "--workspace",
      process.env.BUTLER_V5_WORKSPACE_ROOT ?? repoRoot,
    ])
    console.log("smoke ok [allowlist-slirp]")
  }

  if (livePnpm) {
    const root = mkdtempSync(join(tmpdir(), "allowlist-pnpm-"))
    try {
      writeFileSync(
        join(root, "package.json"),
        JSON.stringify({ name: "allowlist-smoke", private: true }, null, 2),
      )
      runCli("sandbox-probe-allowlist-pnpm", ["--workspace", root])
      console.log("smoke ok [allowlist-pnpm-live]")
    } finally {
      rmSync(root, { recursive: true, force: true })
    }
  }

  console.log("smoke PASS [allowlist-production]")
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
