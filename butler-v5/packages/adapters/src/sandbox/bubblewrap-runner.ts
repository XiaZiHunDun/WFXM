import { resolveSandboxNetworkMode, resolveSandboxEgressIsolation } from "@butler/domain/governance/network-allowlist.js"
import {
  buildSandboxProxyEnv,
  startEgressAllowlistProxy,
  type EgressProxyHandle,
} from "./egress-proxy.js"
import {
  parseProxyPort,
  runInSlirpAllowlistSandbox,
  SLIRP_HOST_GATEWAY,
  canCreateRootlessNetns,
} from "./slirp-egress.js"

export interface SandboxProfile {
  readonly name: string
  readonly workspaceRoot: string
  readonly network: "deny" | "allow" | "allowlist"
  readonly readOnlySystemPaths: readonly string[]
  readonly maxOutputBytes: number
  readonly timeoutMs: number
}

export const DEFAULT_SANDBOX_PROFILE: SandboxProfile = {
  name: "workspace-write-network-deny",
  workspaceRoot: process.cwd(),
  network: "deny",
  readOnlySystemPaths: ["/usr", "/bin", "/lib", "/lib64", "/etc/alternatives"],
  maxOutputBytes: 32 * 1024,
  timeoutMs: 5000,
}

export interface ProcessRunner {
  readonly spawn: (
    command: string,
    args: readonly string[],
    options: {
      readonly cwd?: string
      readonly timeoutMs: number
      readonly maxOutputBytes: number
      readonly env?: NodeJS.ProcessEnv
    },
  ) => Promise<{ readonly code: number; readonly stdout: string; readonly stderr: string }>
}

export interface BubblewrapRunInput {
  readonly argv: readonly string[]
  readonly profile: SandboxProfile
  readonly runner?: ProcessRunner
  readonly bwrapPath?: string
  readonly childEnv?: NodeJS.ProcessEnv
}

export interface BubblewrapRunResult {
  readonly ok: boolean
  readonly stdout?: string
  readonly stderr?: string
  readonly reason?: string
}

export type BubblewrapPreflightResult =
  | { readonly ok: true; readonly bwrapPath: string; readonly version: string }
  | { readonly ok: false; readonly reason: string }

/**
 * Resolve a named sandbox profile. Grant.sandboxProfile elevates from
 * the provider default (network deny) when set to network-allow / allowlist.
 */
export function resolveSandboxProfile(args: {
  readonly workspaceRoot: string
  readonly profileName?: string | null
}): SandboxProfile {
  const name = (args.profileName ?? "").trim() || DEFAULT_SANDBOX_PROFILE.name
  const network =
    name === "workspace-write-network-allow"
      ? "allow"
      : name === "workspace-write-network-allowlist"
        ? "allowlist"
        : "deny"
  return {
    ...DEFAULT_SANDBOX_PROFILE,
    name,
    workspaceRoot: args.workspaceRoot,
    network,
  }
}

/**
 * Unified sandbox entry for local argv side effects (run_command / future MCP local spawn).
 * When `BUTLER_V5_SANDBOX` is not `bubblewrap`, returns `{ ok: true, mode: "disabled" }`
 * so callers fall back to in-process workspace constraints.
 */
export async function executeArgvInSandbox(input: {
  readonly argv: readonly string[]
  readonly workspaceRoot: string
  readonly profileName?: string | null
  readonly networkAllowlist?: readonly string[] | null
  readonly env?: NodeJS.ProcessEnv
  readonly runner?: ProcessRunner
  readonly bwrapPath?: string
}): Promise<
  BubblewrapRunResult | { readonly ok: true; readonly mode: "disabled" }
> {
  const env = input.env ?? process.env
  if ((env["BUTLER_V5_SANDBOX"] ?? "").trim() !== "bubblewrap") {
    return { ok: true, mode: "disabled" }
  }

  const profileName = (input.profileName ?? "").trim()
  const isAllowlistProfile = profileName === "workspace-write-network-allowlist"
  const networkMode = resolveSandboxNetworkMode(env)

  if (isAllowlistProfile && networkMode !== "allowlist") {
    return {
      ok: false,
      reason:
        "network-allowlist Grant requires BUTLER_V5_SANDBOX_NETWORK_MODE=allowlist (fail-closed)",
    }
  }
  if (isAllowlistProfile && (!input.networkAllowlist || input.networkAllowlist.length === 0)) {
    return {
      ok: false,
      reason: "network-allowlist profile requires Grant networkAllowlist (fail-closed)",
    }
  }

  let proxyHandle: EgressProxyHandle | undefined
  let childEnv: NodeJS.ProcessEnv | undefined
  const egressIsolation = resolveSandboxEgressIsolation(env)
  const useSlirpIsolation = isAllowlistProfile && egressIsolation === "slirp"

  try {
    if (isAllowlistProfile && input.networkAllowlist) {
      if (useSlirpIsolation) {
        const netnsOk = input.runner ? await canCreateRootlessNetns(input.runner) : false
        if (!netnsOk) {
          return {
            ok: false,
            reason: "P2d slirp isolation requires rootless unshare -U -r -n (fail-closed)",
          }
        }
        proxyHandle = await startEgressAllowlistProxy(input.networkAllowlist, {
          listenHost: "127.0.0.1",
          env,
        })
        const proxyPort = parseProxyPort(proxyHandle.proxyUrl)
        childEnv = {
          PATH: env["PATH"] ?? "/usr/bin:/bin:/usr/sbin:/sbin",
          ...buildSandboxProxyEnv(`http://${SLIRP_HOST_GATEWAY}:${proxyPort}`),
        }
      } else {
        proxyHandle = await startEgressAllowlistProxy(input.networkAllowlist, { env })
        childEnv = {
          PATH: env["PATH"] ?? "/usr/bin:/bin:/usr/sbin:/sbin",
          ...buildSandboxProxyEnv(proxyHandle.proxyUrl),
        }
      }
    }

    const profile = resolveSandboxProfile({
      workspaceRoot: input.workspaceRoot,
      profileName: input.profileName,
    })

    if (useSlirpIsolation && input.networkAllowlist && childEnv && proxyHandle) {
      if (!input.runner) {
        return { ok: false, reason: "bubblewrap unavailable (fail-closed)" }
      }
      const proxyPort = parseProxyPort(proxyHandle.proxyUrl)
      const bwrapArgs = buildBubblewrapArgs(profile, input.argv, { shareNet: true })
      return await runInSlirpAllowlistSandbox({
        argv: input.argv,
        profile,
        runner: input.runner,
        bwrapArgs,
        ...(input.bwrapPath ? { bwrapPath: input.bwrapPath } : {}),
        childEnv,
        proxyPort,
      })
    }

    return await runInBubblewrap({
      argv: input.argv,
      profile,
      ...(input.runner ? { runner: input.runner } : {}),
      ...(input.bwrapPath ? { bwrapPath: input.bwrapPath } : {}),
      ...(childEnv ? { childEnv } : {}),
    })
  } catch (err) {
    return {
      ok: false,
      reason: err instanceof Error ? err.message : String(err),
    }
  } finally {
    await proxyHandle?.close().catch(() => undefined)
  }
}

/**
 * Verify `bwrap` is on PATH and responds before enabling
 * `BUTLER_V5_SANDBOX=bubblewrap` in production.
 */
export async function preflightBubblewrap(
  bwrapPath = "bwrap",
): Promise<BubblewrapPreflightResult> {
  const { execFile } = await import("node:child_process")
  const { promisify } = await import("node:util")
  const execFileAsync = promisify(execFile)
  try {
    const { stdout } = await execFileAsync(bwrapPath, ["--version"], {
      timeout: 5_000,
      env: { PATH: process.env["PATH"] ?? "/usr/bin:/bin" },
    })
    const version = stdout.trim().split("\n")[0]?.trim() || "unknown"
    return { ok: true, bwrapPath, version }
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err)
    return {
      ok: false,
      reason: `bubblewrap preflight failed (${bwrapPath}): ${detail}`,
    }
  }
}

export function buildBubblewrapArgs(
  profile: SandboxProfile,
  argv: readonly string[],
  options: { readonly shareNet?: boolean } = {},
): string[] {
  const args = ["--die-with-parent"]
  if (options.shareNet) {
    args.push("--share-net")
  } else if (profile.network === "deny") {
    args.push("--unshare-net")
  }
  args.push("--tmpfs", "/tmp", "--bind", profile.workspaceRoot, profile.workspaceRoot)
  for (const path of profile.readOnlySystemPaths) {
    args.push("--ro-bind", path, path)
  }
  args.push("--chdir", profile.workspaceRoot, "--")
  args.push(...argv)
  return args
}

export async function runInBubblewrap(input: BubblewrapRunInput): Promise<BubblewrapRunResult> {
  if (input.argv.length === 0) {
    return { ok: false, reason: "argv must not be empty" }
  }
  if (input.argv[0]?.includes("/")) {
    return { ok: false, reason: "shell-style command paths are not allowed" }
  }

  const bwrap = input.bwrapPath ?? "bwrap"
  const args = buildBubblewrapArgs(input.profile, input.argv)
  const runner = input.runner

  if (!runner) {
    return { ok: false, reason: "bubblewrap unavailable (fail-closed)" }
  }

  const spawnEnv: NodeJS.ProcessEnv = {
    PATH: process.env["PATH"] ?? "/usr/bin:/bin",
    ...(input.childEnv ?? {}),
  }

  try {
    const result = await runner.spawn(bwrap, args, {
      cwd: input.profile.workspaceRoot,
      timeoutMs: input.profile.timeoutMs,
      maxOutputBytes: input.profile.maxOutputBytes,
      env: spawnEnv,
    })
    if (result.code !== 0) {
      return { ok: false, stderr: result.stderr, reason: result.stderr || `exit ${result.code}` }
    }
    return { ok: true, stdout: result.stdout, stderr: result.stderr }
  } catch (err) {
    return {
      ok: false,
      reason: err instanceof Error ? err.message : String(err),
    }
  }
}
