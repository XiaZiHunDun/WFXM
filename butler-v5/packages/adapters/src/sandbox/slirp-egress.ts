import { mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import type { BubblewrapRunResult, ProcessRunner, SandboxProfile } from "./bubblewrap-runner.js"

/** Default slirp4netns host gateway (guest view). */
export const SLIRP_HOST_GATEWAY = "10.0.2.2"

const SLIRP_SETUP_SLEEP_SEC = 1.5

export interface AllowlistDestination {
  readonly ip: string
  readonly port: number
}

export function shellQuote(value: string): string {
  return `'${value.replace(/'/g, `'\\''`)}'`
}

/** Resolve Grant host:port entries to concrete IPv4 destinations for iptables. */
export async function resolveAllowlistDestinations(
  allowlist: readonly string[],
): Promise<readonly AllowlistDestination[]> {
  const { resolve4 } = await import("node:dns/promises")
  const out: AllowlistDestination[] = []
  for (const entry of allowlist) {
    const colon = entry.lastIndexOf(":")
    const host = colon > 0 ? entry.slice(0, colon) : entry
    const port = colon > 0 ? Number(entry.slice(colon + 1)) : 443
    if (!host || !Number.isInteger(port)) continue
    if (/^\d+\.\d+\.\d+\.\d+$/.test(host)) {
      out.push({ ip: host, port })
      continue
    }
    const ips = await resolve4(host)
    for (const ip of ips) out.push({ ip, port })
  }
  return out
}

export function buildSlirpIptablesCommands(args: {
  readonly allowDestinations?: readonly AllowlistDestination[]
  readonly allowHostGatewayPort?: number
}): readonly string[] {
  const cmds = [
    "iptables -w 5 -P OUTPUT DROP",
    "iptables -w 5 -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT",
    "iptables -w 5 -A OUTPUT -o lo -j ACCEPT",
  ]
  if (args.allowHostGatewayPort !== undefined) {
    cmds.push(
      `iptables -w 5 -A OUTPUT -d ${SLIRP_HOST_GATEWAY} -p tcp --dport ${args.allowHostGatewayPort} -j ACCEPT`,
    )
  }
  for (const { ip, port } of args.allowDestinations ?? []) {
    cmds.push(`iptables -w 5 -A OUTPUT -d ${ip} -p tcp --dport ${port} -j ACCEPT`)
  }
  return cmds
}

export function buildSlirpInnerScript(args: {
  readonly bwrapPath: string
  readonly bwrapArgs: readonly string[]
  readonly iptablesCommands: readonly string[]
  readonly commandTimeoutSec: number
}): string {
  const iptables = args.iptablesCommands
    .map((c) => `  ${c.replace(/^iptables /, "$IPTABLES ")}`)
    .join("\n")
  const bwrapCmd = [shellQuote(args.bwrapPath), ...args.bwrapArgs.map(shellQuote)].join(" ")
  return `#!/bin/bash
set -euo pipefail
IPTABLES=$(command -v iptables-legacy || command -v iptables)
SLIRP_PID=""
cleanup() {
  if [ -n "$SLIRP_PID" ]; then
    kill "$SLIRP_PID" 2>/dev/null || true
    wait "$SLIRP_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM HUP
slirp4netns --configure $$ tap0 2>/dev/null &
SLIRP_PID=$!
sleep ${SLIRP_SETUP_SLEEP_SEC}
(
${iptables}
) || { echo "iptables setup failed"; exit 1; }
exec timeout -s KILL ${args.commandTimeoutSec} ${bwrapCmd}
`
}

export function parseProxyPort(proxyUrl: string): number {
  const port = Number(proxyUrl.split(":").at(-1))
  if (!Number.isInteger(port) || port < 1) {
    throw new Error(`invalid egress proxy url: ${proxyUrl}`)
  }
  return port
}

export interface SlirpAllowlistRunInput {
  readonly argv: readonly string[]
  readonly profile: SandboxProfile
  readonly runner: ProcessRunner
  readonly bwrapPath?: string
  readonly bwrapArgs: readonly string[]
  readonly childEnv?: NodeJS.ProcessEnv
  readonly proxyPort: number
  readonly allowDestinations?: readonly AllowlistDestination[]
}

let slirpRunChain: Promise<BubblewrapRunResult> = Promise.resolve({ ok: true })

/** Best-effort: reap slirp4netns orphaned when probe parent died (PPID 1). Never throws. */
export function cleanupOrphanSlirp4netns(): void {
  try {
    for (const name of readdirSync("/proc")) {
      if (!/^\d+$/.test(name)) continue
      const pid = Number(name)
      if (!Number.isFinite(pid) || pid <= 1) continue
      try {
        const cmdline = readFileSync(`/proc/${pid}/cmdline`, "utf8")
        if (!cmdline.includes("slirp4netns")) continue
        const stat = readFileSync(`/proc/${pid}/stat`, "utf8")
        const ppid = Number(stat.split(" ")[3])
        if (ppid === 1) {
          process.kill(pid, "SIGKILL")
        }
      } catch {
        // process exited between readdir and read
      }
    }
  } catch {
    // non-Linux or permission issue — skip
  }
}

/**
 * P2d: rootless netns + slirp + iptables, then bwrap --share-net.
 * Egress to host gateway proxy port only (blocks raw socket bypass of P2c proxy).
 */
export async function runInSlirpAllowlistSandbox(
  input: SlirpAllowlistRunInput,
): Promise<BubblewrapRunResult> {
  const run = async (): Promise<BubblewrapRunResult> => {
  if (input.argv.length === 0) {
    return { ok: false, reason: "argv must not be empty" }
  }

  const bwrapPath = input.bwrapPath ?? "bwrap"
  const bwrapArgs = input.bwrapArgs
  const iptablesCommands = buildSlirpIptablesCommands({
    allowHostGatewayPort: input.proxyPort,
    ...(input.allowDestinations?.length
      ? { allowDestinations: input.allowDestinations }
      : {}),
  })
  const innerScript = buildSlirpInnerScript({
    bwrapPath,
    bwrapArgs,
    iptablesCommands,
    commandTimeoutSec: Math.max(5, Math.ceil(input.profile.timeoutMs / 1000)),
  })

  const tempDir = mkdtempSync(join(tmpdir(), "butler-slirp-"))
  const scriptPath = join(tempDir, "run.sh")
  const xtablesLock = join(tempDir, "xtables.lock")
  writeFileSync(xtablesLock, "")
  writeFileSync(scriptPath, innerScript, { mode: 0o755 })

  const spawnEnv: NodeJS.ProcessEnv = {
    PATH: process.env["PATH"] ?? "/usr/bin:/bin:/usr/sbin:/sbin",
    XTABLES_LOCKFILE: xtablesLock,
    ...(input.childEnv ?? {}),
  }

  try {
    const result = await input.runner.spawn(
      "unshare",
      ["-U", "-r", "-n", "--", "bash", scriptPath],
      {
        cwd: input.profile.workspaceRoot,
        timeoutMs: Math.max(input.profile.timeoutMs, 15_000),
        maxOutputBytes: input.profile.maxOutputBytes,
        env: spawnEnv,
      },
    )
    if (result.code !== 0) {
      const detail = [result.stderr, result.stdout].filter(Boolean).join("\n").trim()
      return {
        ok: false,
        stderr: result.stderr,
        reason: detail || `slirp sandbox exit ${result.code}`,
      }
    }
    return { ok: true, stdout: result.stdout, stderr: result.stderr }
  } catch (err) {
    return {
      ok: false,
      reason: err instanceof Error ? err.message : String(err),
    }
  } finally {
    rmSync(tempDir, { recursive: true, force: true })
    cleanupOrphanSlirp4netns()
  }
  }

  slirpRunChain = slirpRunChain.then(run, run)
  return slirpRunChain
}

/** Quick check: can we create a rootless network namespace on this host? */
export async function canCreateRootlessNetns(runner?: ProcessRunner): Promise<boolean> {
  const r =
    runner ??
    ({
      spawn: async (cmd, args, opts) => {
        const { spawn } = await import("node:child_process")
        return await new Promise((resolve) => {
          const child = spawn(cmd, [...args], {
            cwd: opts.cwd,
            env: opts.env ?? process.env,
            stdio: ["ignore", "pipe", "pipe"],
          })
          child.on("close", (code) => resolve({ code: code ?? 1, stdout: "", stderr: "" }))
        })
      },
    } satisfies ProcessRunner)

  const result = await r.spawn("unshare", ["-U", "-r", "-n", "--", "true"], {
    timeoutMs: 3000,
    maxOutputBytes: 256,
  })
  return result.code === 0
}
