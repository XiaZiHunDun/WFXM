#!/usr/bin/env node
import { homedir } from "node:os"
import { join } from "node:path"
import { Command } from "commander"
import { serve } from "@hono/node-server"
import { runWechatLogin } from "./wechat-login.js"

const program = new Command()

program.name("butler").description("Butler v5 CLI").version("0.0.1")

program
  .command("start")
  .description("Start the v5 wiring (server)")
  .action(async () => {
    const { default: app, startIlinkPollerIfEnabled } = await import("@butler/api")
    const port = Number(process.env["PORT"] ?? 3000)
    let stopIlink: (() => void) | undefined
    const server = serve({ fetch: app.fetch, port }, () => {
      console.log(`v5 wiring listening on :${port}`)
      const handle = startIlinkPollerIfEnabled(process.env)
      stopIlink = handle?.stop
    })
    const shutdown = (): void => {
      stopIlink?.()
      server.close(() => process.exit(0))
    }
    process.on("SIGINT", shutdown)
    process.on("SIGTERM", shutdown)
  })

program
  .command("wechat-login")
  .description("Scan iLink QR and write WECHAT_TOKEN into ~/.config/butler-v5/env")
  .action(async () => {
    const envPath =
      process.env["BUTLER_V5_ENV_PATH"] ?? join(homedir(), ".config", "butler-v5", "env")
    const result = await runWechatLogin({
      envPath,
      ...(process.env["WECHAT_BASE_URL"] ? { baseUrl: process.env["WECHAT_BASE_URL"] } : {}),
    })
    if (!result.ok) {
      console.error(result.reason)
      process.exit(1)
    }
  })

program
  .command("approvals")
  .description("List pending approval steps (Owner API loopback)")
  .option("--api <url>", "API base URL", "http://127.0.0.1:3000")
  .action(async (opts: { api: string }) => {
    const token = (process.env["BUTLER_V5_OWNER_TOKEN"] ?? "").trim()
    if (!token) {
      console.error("BUTLER_V5_OWNER_TOKEN is required")
      process.exit(1)
    }
    const res = await fetch(`${opts.api}/v1/owner/approvals`, {
      headers: { authorization: `Bearer ${token}` },
    })
    console.log(await res.text())
  })

program
  .command("approve")
  .description("Approve a waiting_approval step by id")
  .argument("<stepId>", "approval step id")
  .option("--api <url>", "API base URL", "http://127.0.0.1:3000")
  .option("--capability <name>", "granted capability", "run_command")
  .action(async (stepId: string, opts: { api: string; capability: string }) => {
    const token = (process.env["BUTLER_V5_OWNER_TOKEN"] ?? "").trim()
    if (!token) {
      console.error("BUTLER_V5_OWNER_TOKEN is required")
      process.exit(1)
    }
    const res = await fetch(
      `${opts.api}/v1/owner/approvals/${encodeURIComponent(stepId)}/approve`,
      {
        method: "POST",
        headers: {
          authorization: `Bearer ${token}`,
          "content-type": "application/json",
        },
        body: JSON.stringify({ capabilities: [opts.capability] }),
      },
    )
    console.log(await res.text())
  })

program
  .command("deny")
  .description("Deny a waiting_approval step by id")
  .argument("<stepId>", "approval step id")
  .option("--api <url>", "API base URL", "http://127.0.0.1:3000")
  .action(async (stepId: string, opts: { api: string }) => {
    const token = (process.env["BUTLER_V5_OWNER_TOKEN"] ?? "").trim()
    if (!token) {
      console.error("BUTLER_V5_OWNER_TOKEN is required")
      process.exit(1)
    }
    const res = await fetch(`${opts.api}/v1/owner/approvals/${encodeURIComponent(stepId)}/deny`, {
      method: "POST",
      headers: { authorization: `Bearer ${token}` },
    })
    console.log(await res.text())
  })

program
  .command("sandbox-preflight")
  .description("Verify bubblewrap (bwrap) is available for BUTLER_V5_SANDBOX=bubblewrap")
  .option("--bwrap <path>", "bwrap binary path", "bwrap")
  .action(async (opts: { bwrap: string }) => {
    const { preflightBubblewrap } = await import("@butler/adapters/sandbox/bubblewrap-runner.js")
    const sandbox = (process.env["BUTLER_V5_SANDBOX"] ?? "").trim()
    if (sandbox === "bubblewrap") {
      console.error("BUTLER_V5_SANDBOX=bubblewrap — checking bwrap…")
    }
    const result = await preflightBubblewrap(opts.bwrap)
    if (!result.ok) {
      console.error(result.reason)
      console.error(
        "Install bubblewrap (e.g. apt install bubblewrap) or unset BUTLER_V5_SANDBOX.",
      )
      process.exit(1)
    }
    console.log(`bubblewrap ok: ${result.bwrapPath} (${result.version})`)
  })

program
  .command("verify")
  .description("Verify v5 wiring (placeholder)")
  .action(() => {
    console.log("v5 verify: stub (R7.3)")
  })

program.parseAsync(process.argv).catch((err) => {
  console.error(err)
  process.exit(1)
})
