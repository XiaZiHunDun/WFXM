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
  .command("schedule")
  .description("Schedule / heartbeat (Owner API)")
  .argument("<action>", "tick — run one schedule evaluation pass")
  .option("--api <url>", "API base URL", "http://127.0.0.1:3000")
  .action(async (action: string, opts: { api: string }) => {
    if (action !== "tick") {
      console.error("action must be tick")
      process.exit(1)
    }
    const res = await fetch(`${opts.api}/v1/owner/schedule/tick`, { method: "POST" })
    console.log(await res.text())
    if (!res.ok) process.exit(1)
  })

program
  .command("conversations")
  .description("List conversations for a project (Owner API loopback)")
  .requiredOption("--project <id>", "project id (e.g. wechat, WFXM, proj-x)")
  .option("--api <url>", "API base URL", "http://127.0.0.1:3000")
  .option("--limit <n>", "max rows", "50")
  .option("--json", "pretty-print JSON response")
  .action(async (opts: { api: string; project: string; limit: string; json?: boolean }) => {
    const qs = new URLSearchParams({
      projectId: opts.project,
      limit: opts.limit,
    })
    const res = await fetch(`${opts.api}/v1/owner/conversations?${qs.toString()}`)
    const text = await res.text()
    if (opts.json) {
      try {
        console.log(JSON.stringify(JSON.parse(text), null, 2))
      } catch {
        console.log(text)
      }
    } else {
      console.log(text)
    }
    if (!res.ok) process.exit(1)
  })

program
  .command("approvals")
  .description("List pending approval steps (Owner API loopback)")
  .option("--api <url>", "API base URL", "http://127.0.0.1:3000")
  .action(async (opts: { api: string }) => {
    const res = await fetch(`${opts.api}/v1/owner/approvals`)
    console.log(await res.text())
  })

program
  .command("approve")
  .description("Approve a waiting_approval step by id")
  .argument("<stepId>", "approval step id")
  .option("--api <url>", "API base URL", "http://127.0.0.1:3000")
  .option("--capability <name>", "granted capability", "run_command")
  .option("--elevate-network", "stamp Grant sandboxProfile=network-allow")
  .option(
    "--network-allowlist <hosts>",
    "comma-separated host:port list (e.g. registry.npmjs.org:443,pypi.org:443)",
  )
  .action(
    async (
      stepId: string,
      opts: { api: string; capability: string; elevateNetwork?: boolean; networkAllowlist?: string },
    ) => {
    const networkAllowlist = opts.networkAllowlist
      ?.split(",")
      .map((part) => part.trim())
      .filter((part) => part.length > 0)
    const res = await fetch(
      `${opts.api}/v1/owner/approvals/${encodeURIComponent(stepId)}/approve`,
      {
        method: "POST",
        headers: {
          "content-type": "application/json",
        },
        body: JSON.stringify({
          capabilities: [opts.capability],
          ...(opts.elevateNetwork ? { elevateNetwork: true } : {}),
          ...(networkAllowlist && networkAllowlist.length > 0
            ? { networkAllowlist }
            : {}),
        }),
      },
    )
    console.log(await res.text())
  },
  )

program
  .command("deny")
  .description("Deny a waiting_approval step by id")
  .argument("<stepId>", "approval step id")
  .option("--api <url>", "API base URL", "http://127.0.0.1:3000")
  .action(async (stepId: string, opts: { api: string }) => {
    const res = await fetch(`${opts.api}/v1/owner/approvals/${encodeURIComponent(stepId)}/deny`, {
      method: "POST",
    })
    console.log(await res.text())
  })

program
  .command("cancel")
  .description("Cancel an active Run by id (Owner API)")
  .argument("<runId>", "run id")
  .option("--api <url>", "API base URL", "http://127.0.0.1:3000")
  .option("--reason <text>", "cancel reason")
  .action(async (runId: string, opts: { api: string; reason?: string }) => {
    const res = await fetch(`${opts.api}/v1/owner/runs/${encodeURIComponent(runId)}/cancel`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        subject: "owner",
        ...(opts.reason ? { reason: opts.reason } : {}),
      }),
    })
    console.log(await res.text())
    if (!res.ok) process.exit(1)
  })

program
  .command("expire-runs")
  .description("Expire active Runs past their deadline (Owner API)")
  .option("--api <url>", "API base URL", "http://127.0.0.1:3000")
  .action(async (opts: { api: string }) => {
    const res = await fetch(`${opts.api}/v1/owner/runs/expire-overdue`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ subject: "owner" }),
    })
    console.log(await res.text())
    if (!res.ok) process.exit(1)
  })

program
  .command("run")
  .description("Run a one-shot goal through the v5 butler loop (CLI RunTrigger)")
  .argument("<goal>", "goal text")
  .option("--subject <id>", "owner subject for policy evaluation")
  .option("--conversation-id <id>", "reuse an existing conversation id")
  .action(async (goal: string, opts: { subject?: string; conversationId?: string }) => {
    const { createProductionWiring } = await import("@butler/api/bootstrap-wiring.js")
    const { runCliGoal } = await import("@butler/api/cli-run.js")
    const boot = await createProductionWiring(process.env)
    if (!boot.ok) {
      console.error(boot.reason)
      process.exit(1)
    }
    try {
      const result = await runCliGoal({
        wiring: boot.value.wiring,
        goal,
        ...(opts.subject ? { subject: opts.subject } : {}),
        ...(opts.conversationId ? { conversationId: opts.conversationId } : {}),
      })
      console.log(result.reply)
      if (result.finalDecision === "WaitForApproval") {
        process.exit(2)
      }
    } finally {
      await boot.value.close()
    }
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
  .command("sandbox-probe")
  .description(
    "Verify network-deny blocks and network-allow reaches probe URL (Grant elevateNetwork path)",
  )
  .option("--workspace <path>", "workspace root for bwrap bind")
  .option("--probe-url <url>", "HTTP URL to fetch inside sandbox", "http://127.0.0.1:3000/healthz")
  .action(async (opts: { workspace?: string; probeUrl: string }) => {
    const {
      createDefaultProcessRunner,
      probeSandboxNetworkIsolation,
    } = await import("@butler/adapters/sandbox/sandbox-probe.js")
    const workspaceRoot =
      (opts.workspace ?? process.env["BUTLER_V5_WORKSPACE_ROOT"] ?? process.cwd()).trim()
    const productionEnabled =
      (process.env["BUTLER_V5_SANDBOX"] ?? "").trim() === "bubblewrap"
    const result = await probeSandboxNetworkIsolation({
      workspaceRoot,
      env: { ...process.env, BUTLER_V5_SANDBOX: "bubblewrap" },
      runner: createDefaultProcessRunner(),
      probeUrl: opts.probeUrl,
    })
    if (!productionEnabled) {
      console.error(
        "note: BUTLER_V5_SANDBOX not set in shell; probe forced bubblewrap for isolation check",
      )
    }
    console.log(
      `sandbox probe: denyBlocked=${result.denyBlockedNetwork} allowReached=${result.allowReachedNetwork} url=${result.probeUrl}`,
    )
    if (!result.ok) {
      console.error(result.reason ?? "sandbox network probe failed")
      process.exit(1)
    }
    console.log("sandbox network probe ok")
  })

program
  .command("sandbox-probe-allowlist")
  .description("Verify Grant networkAllowlist egress proxy allows/blocks host:port (P2c)")
  .option("--workspace <path>", "workspace root for bwrap bind")
  .action(async (opts: { workspace?: string }) => {
    const {
      createDefaultProcessRunner,
      probeSandboxAllowlistEgress,
    } = await import("@butler/adapters/sandbox/sandbox-probe.js")
    const workspaceRoot =
      (opts.workspace ?? process.env["BUTLER_V5_WORKSPACE_ROOT"] ?? process.cwd()).trim()
    const result = await probeSandboxAllowlistEgress({
      workspaceRoot,
      runner: createDefaultProcessRunner(),
    })
    console.log(
      `allowlist probe: allowed=${result.allowedReachable} blocked=${result.blockedReachable}`,
    )
    if (!result.ok) {
      console.error(result.reason ?? "allowlist egress probe failed")
      process.exit(1)
    }
    console.log("sandbox allowlist probe ok")
  })

program
  .command("sandbox-probe-allowlist-slirp")
  .description("Verify P2d slirp netns blocks raw socket bypass (needs slirp4netns + unshare)")
  .option("--workspace <path>", "workspace root for bwrap bind")
  .action(async (opts: { workspace?: string }) => {
    const {
      createDefaultProcessRunner,
      probeSandboxAllowlistSlirpIsolation,
    } = await import("@butler/adapters/sandbox/sandbox-probe.js")
    const workspaceRoot =
      (opts.workspace ?? process.env["BUTLER_V5_WORKSPACE_ROOT"] ?? process.cwd()).trim()
    const result = await probeSandboxAllowlistSlirpIsolation({
      workspaceRoot,
      env: {
        ...process.env,
        BUTLER_V5_SANDBOX_EGRESS_ISOLATION: "slirp",
      },
      runner: createDefaultProcessRunner(),
    })
    console.log(
      `slirp probe: rawBlocked=${result.rawSocketBlocked} proxyPath=${result.proxyPathReachable}`,
    )
    if (!result.ok) {
      console.error(result.reason ?? "slirp allowlist probe failed")
      process.exit(1)
    }
    console.log("sandbox allowlist slirp probe ok")
  })

program
  .command("sandbox-p2d-preflight")
  .description("Check host readiness for P2d slirp+iptables spike (binaries + caps)")
  .action(async () => {
    const { preflightP2dSlirpEgress } = await import("@butler/adapters/sandbox/p2d-preflight.js")
    const result = preflightP2dSlirpEgress()
    for (const check of result.checks) {
      console.log(`${check.ok ? "ok" : "FAIL"} ${check.name}: ${check.detail}`)
    }
    console.log(result.note)
    if (!result.readyForSpike) process.exit(1)
  })

program
  .command("sandbox-probe-allowlist-pnpm")
  .description("Live npm registry HTTPS fetch via allowlist egress proxy (needs network)")
  .option("--workspace <path>", "workspace root for bwrap bind")
  .action(async (opts: { workspace?: string }) => {
    const { probeAllowlistPnpmRegistry } = await import(
      "@butler/adapters/sandbox/sandbox-probe.js"
    )
    const { probeSandboxAllowlistEgress, createDefaultProcessRunner } = await import(
      "@butler/adapters/sandbox/sandbox-probe.js"
    )
    const workspaceRoot =
      (opts.workspace ?? process.env["BUTLER_V5_WORKSPACE_ROOT"] ?? process.cwd()).trim()
    const local = await probeSandboxAllowlistEgress({
      workspaceRoot,
      runner: createDefaultProcessRunner(),
    })
    if (!local.ok) {
      console.error(local.reason ?? "local allowlist probe failed")
      process.exit(1)
    }
    const live = await probeAllowlistPnpmRegistry({ workspaceRoot })
    if (!live.ok) {
      console.error(live.reason ?? "pnpm registry probe failed")
      process.exit(1)
    }
    console.log(`registry allowlist ok: ${(live.output ?? "").trim()}`)
  })

program
  .command("memory")
  .description("List or add Durable Memory via Owner API")
  .argument("<action>", "list | add | confirm | reject | delete")
  .argument("[arg]", "content for add, or memoryId for confirm/reject/delete")
  .option("--api <url>", "API base URL", "http://127.0.0.1:3000")
  .option("--subject <id>", "memory subject", "owner")
  .action(async (action: string, arg: string | undefined, opts: { api: string; subject: string }) => {
    const headers = {
      "content-type": "application/json",
    }
    if (action === "list") {
      const res = await fetch(
        `${opts.api}/v1/owner/memories?subject=${encodeURIComponent(opts.subject)}`,
        { headers },
      )
      console.log(await res.text())
      if (!res.ok) process.exit(1)
      return
    }
    if (action === "add") {
      if (!arg?.trim()) {
        console.error("usage: butler memory add <content>")
        process.exit(1)
      }
      const res = await fetch(`${opts.api}/v1/owner/memories`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          subject: opts.subject,
          content: arg,
          sourceKind: "owner",
        }),
      })
      console.log(await res.text())
      if (!res.ok) process.exit(1)
      return
    }
    if (action === "confirm" || action === "reject" || action === "delete") {
      if (!arg?.trim()) {
        console.error(`usage: butler memory ${action} <memoryId>`)
        process.exit(1)
      }
      const res = await fetch(
        action === "delete"
          ? `${opts.api}/v1/owner/memories/${arg}`
          : `${opts.api}/v1/owner/memories/${arg}/${action}`,
        {
          method: action === "delete" ? "DELETE" : "POST",
          headers,
        },
      )
      console.log(await res.text())
      if (!res.ok) process.exit(1)
      return
    }
    console.error("action must be list | add | confirm | reject | delete")
    process.exit(1)
  })

program
  .command("project-knowledge")
  .description("Project Knowledge ingest/list via Owner API (WFXM MVP)")
  .argument("<action>", "list | add | get | delete | promote-doc | snapshot | sync")
  .argument("[arg]", "item id, document id, or note content")
  .option("--api <url>", "API base URL", "http://127.0.0.1:3000")
  .option("--project <id>", "project id", "WFXM")
  .option("--kind <kind>", "note | document | workspace_snapshot", "note")
  .option("--title <title>", "optional title")
  .option("--path <path>", "relative path for snapshot")
  .action(
    async (
      action: string,
      arg: string | undefined,
      opts: { api: string; project: string; kind: string; title?: string; path?: string },
    ) => {
      const headers = { "content-type": "application/json" }
      const base = `${opts.api}/v1/owner/project-knowledge`
      if (action === "list") {
        const res = await fetch(`${base}?projectId=${encodeURIComponent(opts.project)}`, { headers })
        console.log(await res.text())
        if (!res.ok) process.exit(1)
        return
      }
      if (action === "add") {
        if (!arg?.trim()) {
          console.error("usage: butler project-knowledge add <content>")
          process.exit(1)
        }
        const res = await fetch(base, {
          method: "POST",
          headers,
          body: JSON.stringify({
            projectId: opts.project,
            kind: opts.kind === "note" ? "manual_note" : opts.kind,
            title: opts.title,
            text: arg,
          }),
        })
        console.log(await res.text())
        if (!res.ok) process.exit(1)
        return
      }
      if (action === "get") {
        if (!arg?.trim()) {
          console.error("usage: butler project-knowledge get <id>")
          process.exit(1)
        }
        const res = await fetch(`${base}/${arg}`, { headers })
        console.log(await res.text())
        if (!res.ok) process.exit(1)
        return
      }
      if (action === "delete") {
        if (!arg?.trim()) {
          console.error("usage: butler project-knowledge delete <id>")
          process.exit(1)
        }
        const res = await fetch(`${base}/${arg}`, { method: "DELETE", headers })
        console.log(await res.text())
        if (!res.ok) process.exit(1)
        return
      }
      if (action === "promote-doc") {
        if (!arg?.trim()) {
          console.error("usage: butler project-knowledge promote-doc <documentId>")
          process.exit(1)
        }
        const res = await fetch(
          `${opts.api}/v1/owner/documents/${encodeURIComponent(arg)}/promote-project-knowledge`,
          {
            method: "POST",
            headers,
            body: JSON.stringify({ projectId: opts.project }),
          },
        )
        console.log(await res.text())
        if (!res.ok) process.exit(1)
        return
      }
      if (action === "snapshot") {
        if (!opts.path?.trim()) {
          console.error("usage: butler project-knowledge snapshot --path <relative-path>")
          process.exit(1)
        }
        const res = await fetch(base, {
          method: "POST",
          headers,
          body: JSON.stringify({
            projectId: opts.project,
            kind: "file_snapshot",
            title: opts.title ?? opts.path,
            filePath: opts.path,
          }),
        })
        console.log(await res.text())
        if (!res.ok) process.exit(1)
        return
      }
      if (action === "sync") {
        const res = await fetch(`${base}/sync`, { method: "POST", headers })
        console.log(await res.text())
        if (!res.ok) process.exit(1)
        return
      }
      console.error("action must be list | add | get | delete | promote-doc | snapshot | sync")
      process.exit(1)
    },
  )

program
  .command("document")
  .description("Ingest or manage documents via Owner API")
  .argument("<action>", "list | add | get | delete | promote")
  .argument("[arg]", "title for add, or documentId for get/delete/promote")
  .option("--api <url>", "API base URL", "http://127.0.0.1:3000")
  .option("--subject <id>", "document subject", "owner")
  .option("--format <fmt>", "plaintext | markdown | pdf", "plaintext")
  .option("--text <body>", "extracted text body for add")
  .option("--file <path>", "read UTF-8 text from file for add")
  .action(
    async (
      action: string,
      arg: string | undefined,
      opts: {
        api: string
        subject: string
        format: string
        text?: string
        file?: string
      },
    ) => {
      const headers = {
        "content-type": "application/json",
      }
      if (action === "list") {
        const res = await fetch(
          `${opts.api}/v1/owner/documents?subject=${encodeURIComponent(opts.subject)}`,
          { headers },
        )
        console.log(await res.text())
        if (!res.ok) process.exit(1)
        return
      }
      if (action === "add") {
        const { readFileSync } = await import("node:fs")
        const title = arg?.trim()
        if (!title) {
          console.error("usage: butler document add <title> --text ... | --file ...")
          process.exit(1)
        }
        let text = opts.text ?? ""
        if (opts.file) {
          text = readFileSync(opts.file, "utf8")
        }
        const res = await fetch(`${opts.api}/v1/owner/documents`, {
          method: "POST",
          headers,
          body: JSON.stringify({
            subject: opts.subject,
            title,
            format: opts.format,
            text,
            ...(opts.file ? { provenance: { sourcePath: opts.file } } : {}),
          }),
        })
        console.log(await res.text())
        if (!res.ok) process.exit(1)
        return
      }
      if (action === "get" || action === "delete" || action === "promote") {
        if (!arg?.trim()) {
          console.error(`usage: butler document ${action} <documentId>`)
          process.exit(1)
        }
        const url =
          action === "promote"
            ? `${opts.api}/v1/owner/documents/${arg}/promote-memory`
            : `${opts.api}/v1/owner/documents/${arg}`
        const res = await fetch(url, {
          method: action === "get" ? "GET" : action === "delete" ? "DELETE" : "POST",
          headers,
          ...(action === "promote" ? { body: "{}" } : {}),
        })
        console.log(await res.text())
        if (!res.ok) process.exit(1)
        return
      }
      console.error("action must be list | add | get | delete | promote")
      process.exit(1)
    },
  )

program
  .command("traces")
  .description("List or clear local traces (Owner API)")
  .argument("[action]", "list (default) | clear", "list")
  .option("--api <url>", "API base URL", "http://127.0.0.1:3000")
  .option("--run-id <id>", "filter by runId")
  .option("--conversation-id <id>", "filter by conversationId")
  .option("--kind <kind>", "run|step|capability|policy|grant|approval")
  .option("--limit <n>", "max events", "100")
  .action(
    async (
      action: string,
      opts: {
        api: string
        runId?: string
        conversationId?: string
        kind?: string
        limit: string
      },
    ) => {
      const headers = {
        "content-type": "application/json",
      }
      if (action === "clear") {
        const res = await fetch(`${opts.api}/v1/owner/traces/clear`, {
          method: "POST",
          headers,
          body: "{}",
        })
        console.log(await res.text())
        if (!res.ok) process.exit(1)
        return
      }
      const qs = new URLSearchParams()
      if (opts.runId) qs.set("runId", opts.runId)
      if (opts.conversationId) qs.set("conversationId", opts.conversationId)
      if (opts.kind) qs.set("kind", opts.kind)
      qs.set("limit", opts.limit)
      const res = await fetch(`${opts.api}/v1/owner/traces?${qs.toString()}`, { headers })
      console.log(await res.text())
      if (!res.ok) process.exit(1)
    },
  )

program
  .command("task")
  .description("Manage Tasks / Procedures via Owner API")
  .argument("<action>", "list | add | run | done | proc-list | proc-add")
  .argument("[arg]", "title for add, taskId for run/done, or procedure JSON for proc-add")
  .option("--api <url>", "API base URL", "http://127.0.0.1:3000")
  .option("--subject <id>", "task subject", "owner")
  .option("--goal <text>", "goal for add")
  .option("--procedure-id <id>", "bind procedure on add")
  .action(
    async (
      action: string,
      arg: string | undefined,
      opts: { api: string; subject: string; goal?: string; procedureId?: string },
    ) => {
      const headers = {
        "content-type": "application/json",
      }
      if (action === "list") {
        const res = await fetch(
          `${opts.api}/v1/owner/tasks?subject=${encodeURIComponent(opts.subject)}`,
          { headers },
        )
        console.log(await res.text())
        if (!res.ok) process.exit(1)
        return
      }
      if (action === "proc-list") {
        const res = await fetch(`${opts.api}/v1/owner/procedures`, { headers })
        console.log(await res.text())
        if (!res.ok) process.exit(1)
        return
      }
      if (action === "proc-add") {
        if (!arg?.trim()) {
          console.error('usage: butler task proc-add \'{"name":"x","steps":[...]}\'')
          process.exit(1)
        }
        const res = await fetch(`${opts.api}/v1/owner/procedures`, {
          method: "POST",
          headers,
          body: arg,
        })
        console.log(await res.text())
        if (!res.ok) process.exit(1)
        return
      }
      if (action === "add") {
        if (!arg?.trim() || !opts.goal?.trim()) {
          console.error("usage: butler task add <title> --goal <text> [--procedure-id id]")
          process.exit(1)
        }
        const res = await fetch(`${opts.api}/v1/owner/tasks`, {
          method: "POST",
          headers,
          body: JSON.stringify({
            subject: opts.subject,
            title: arg,
            goal: opts.goal,
            ...(opts.procedureId
              ? { procedureId: opts.procedureId, procedureStepIndex: 0 }
              : {}),
          }),
        })
        console.log(await res.text())
        if (!res.ok) process.exit(1)
        return
      }
      if (action === "run" || action === "done") {
        if (!arg?.trim()) {
          console.error(`usage: butler task ${action} <taskId>`)
          process.exit(1)
        }
        const res = await fetch(`${opts.api}/v1/owner/tasks/${arg}/${action}`, {
          method: "POST",
          headers,
          body: "{}",
        })
        console.log(await res.text())
        if (!res.ok) process.exit(1)
        return
      }
      console.error("action must be list | add | run | done | proc-list | proc-add")
      process.exit(1)
    },
  )

program
  .command("mcp")
  .description("MCP Owner operations (loopback API)")
  .argument("<action>", "status | revoke-grants")
  .argument("[serverId]", "MCP server id (revoke-grants)")
  .option("--api <url>", "API base URL", "http://127.0.0.1:3000")
  .action(async (action: string, serverId: string | undefined, opts: { api: string }) => {
    const base = opts.api.replace(/\/$/, "")
    if (action === "status") {
      const res = await fetch(`${base}/v1/owner/mcp/status`)
      console.log(await res.text())
      if (!res.ok) process.exit(1)
      return
    }
    if (action === "revoke-grants") {
      const id = (serverId ?? "").trim()
      if (!id) {
        console.error("serverId required for revoke-grants")
        process.exit(1)
      }
      const res = await fetch(
        `${base}/v1/owner/mcp/servers/${encodeURIComponent(id)}/revoke-grants`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ subject: "owner" }),
        },
      )
      console.log(await res.text())
      if (!res.ok) process.exit(1)
      return
    }
    console.error(`unknown mcp action: ${action}`)
    process.exit(1)
  })

program
  .command("verify")
  .description("Verify v5 migrations registry and optional Owner API health")
  .option("--api <url>", "API base URL to ping /healthz", "")
  .action(async (opts: { api: string }) => {
    const { listMigrationFiles } = await import("@butler/persistence")
    const files = listMigrationFiles()
    const required = [
      "0004_durable_memory.sql",
      "0005_documents.sql",
      "0006_task_procedure.sql",
      "0010_project_knowledge.sql",
    ] as const
    const missing = required.filter((name) => !files.includes(name))
    if (missing.length > 0) {
      console.error(`verify failed: missing migrations ${missing.join(", ")}`)
      process.exit(1)
    }
    console.log(`v5 verify: migrations ok (${files.length} files)`)
    for (const name of files) console.log(`  - ${name}`)

    const api = opts.api.trim()
    if (!api) return
    const res = await fetch(`${api.replace(/\/$/, "")}/healthz`)
    const text = await res.text()
    if (!res.ok) {
      console.error(`verify failed: /healthz ${res.status} ${text}`)
      process.exit(1)
    }
    console.log(`v5 verify: healthz ok ${text}`)
  })

program.parseAsync(process.argv).catch((err) => {
  console.error(err)
  process.exit(1)
})
