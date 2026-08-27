import { resolveSandboxNetworkMode, resolveSandboxEgressIsolation } from "@butler/domain/governance/network-allowlist.js"
import {
  buildSandboxProxyEnv,
  startEgressAllowlistProxy,
  type EgressProxyHandle,
} from "./egress-proxy.js"
import {
  cleanupOrphanSlirp4netns,
  parseProxyPort,
  runInSlirpAllowlistSandbox,
  SLIRP_HOST_GATEWAY,
  canCreateRootlessNetns,
} from "./slirp-egress.js"

/**
 * Resolve the sandbox scratch disk quota from `BUTLER_V5_SANDBOX_MAX_FILE_BYTES`.
 * Enforced as RLIMIT_FSIZE on the bwrap child (inherited by the sandboxed
 * command). Returns the cap in bytes, or null when unset/0/invalid (no cap).
 * `/tmp` is already a tmpfs inside the sandbox, so scratch cannot grow the host
 * disk; the RLIMIT caps max single-file size written anywhere in the sandbox.
 */
export function resolveSandboxFileQuotaBytes(
  env: Readonly<Record<string, string | undefined>> = {},
): number | null {
  const raw = (env["BUTLER_V5_SANDBOX_MAX_FILE_BYTES"] ?? "").trim()
  if (raw === "") return null
  const n = Number(raw)
  if (!Number.isSafeInteger(n) || n <= 0) return null
  return n
}

/** Prefix `argv` with `prlimit --fsize=N:N --` when a quota is set, else pass through. */
export function wrapWithFileSizeLimit(
  argv: readonly string[],
  bytes: number | null,
): readonly string[] {
  if (bytes !== null && bytes > 0) {
    return ["prlimit", `--fsize=${bytes}:${bytes}`, "--", ...argv]
  }
  return argv
}

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
  readOnlySystemPaths: ["/usr", "/bin", "/lib", "/lib64", "/etc/alternatives", "/etc/ssl"],
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
  /** P2 host-injected credentials, merged verbatim into the child env. */
  readonly injectEnv?: Readonly<Record<string, string>>
  readonly runner?: ProcessRunner
  readonly bwrapPath?: string
}): Promise<
  BubblewrapRunResult | { readonly ok: true; readonly mode: "disabled" }
> {
  const env = input.env ?? process.env
  const injectEnv = input.injectEnv ?? {}
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

  function slirpFallbackEnabled(): boolean {
    const raw = (env["BUTLER_V5_SANDBOX_SLIRP_FALLBACK"] ?? "1").trim().toLowerCase()
    return raw === "1" || raw === "true" || raw === "yes"
  }

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
          ...injectEnv,
        }
      } else {
        proxyHandle = await startEgressAllowlistProxy(input.networkAllowlist, { env })
        childEnv = {
          PATH: env["PATH"] ?? "/usr/bin:/bin:/usr/sbin:/sbin",
          ...buildSandboxProxyEnv(proxyHandle.proxyUrl),
          ...injectEnv,
        }
      }
    }

    const profile = resolveSandboxProfile({
      workspaceRoot: input.workspaceRoot,
      ...(input.profileName !== undefined ? { profileName: input.profileName } : {}),
    })
    const profileWithTimeout =
      useSlirpIsolation && profile.network === "allowlist"
        ? {
            ...profile,
            timeoutMs: Math.max(
              profile.timeoutMs,
              Number(env["BUTLER_V5_RUN_COMMAND_TIMEOUT_MS"]) > 0
                ? Number(env["BUTLER_V5_RUN_COMMAND_TIMEOUT_MS"])
                : 120_000,
            ),
          }
        : profile

    if (useSlirpIsolation && input.networkAllowlist && childEnv && proxyHandle) {
      if (!input.runner) {
        return { ok: false, reason: "bubblewrap unavailable (fail-closed)" }
      }
      const proxyPort = parseProxyPort(proxyHandle.proxyUrl)
      const quotaBytes = resolveSandboxFileQuotaBytes(env)
      const bwrapArgs = wrapWithFileSizeLimit(
        buildBubblewrapArgs(profile, input.argv, { shareNet: true }),
        quotaBytes,
      )
      const slirpResult = await runInSlirpAllowlistSandbox({
        argv: input.argv,
        profile: profileWithTimeout,
        runner: input.runner,
        bwrapArgs,
        ...(input.bwrapPath ? { bwrapPath: input.bwrapPath } : {}),
        childEnv,
        proxyPort,
      })
      if (slirpResult.ok || !slirpFallbackEnabled() || !input.runner) {
        return slirpResult
      }
      const proxyOnlyEnv: NodeJS.ProcessEnv = {
        PATH: env["PATH"] ?? "/usr/bin:/bin:/usr/sbin:/sbin",
        ...buildSandboxProxyEnv(proxyHandle.proxyUrl),
        ...injectEnv,
      }
      return await runInBubblewrap({
        argv: input.argv,
        profile,
        runner: input.runner,
        childEnv: proxyOnlyEnv,
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

/**
 * Production ProcessRunner: detached process groups + slirp orphan cleanup.
 * Required for P2d slirp allowlist (workspace-tools must not use a bare spawn).
 */
export function createDefaultProcessRunner(): ProcessRunner {
  return {
    spawn: async (command, args, opts) => {
      const { spawn } = await import("node:child_process")
      const spawnEnv = {
        PATH: process.env["PATH"] ?? "/usr/bin:/bin",
        ...(opts.env ?? {}),
      }
      return await new Promise((resolvePromise) => {
        let child: ReturnType<typeof spawn>
        let settled = false
        const outChunks: Buffer[] = []
        const errChunks: Buffer[] = []
        let outTotal = 0
        let errTotal = 0
        try {
          child = spawn(command, [...args], {
            cwd: opts.cwd,
            env: spawnEnv,
            stdio: ["ignore", "pipe", "pipe"],
            detached: true,
          })
        } catch (err) {
          resolvePromise({
            code: 1,
            stdout: "",
            stderr: err instanceof Error ? err.message : String(err),
          })
          return
        }
        const takeOut = (buf: Buffer) => {
          outTotal += buf.length
          if (outTotal <= opts.maxOutputBytes) outChunks.push(buf)
        }
        const takeErr = (buf: Buffer) => {
          errTotal += buf.length
          if (errTotal <= opts.maxOutputBytes) errChunks.push(buf)
        }
        child.stdout?.on("data", (b: Buffer) => takeOut(b))
        child.stderr?.on("data", (b: Buffer) => takeErr(b))
        const finish = (code: number) => {
          if (settled) return
          settled = true
          clearTimeout(timer)
          resolvePromise({
            code,
            stdout: Buffer.concat(outChunks).toString("utf8"),
            stderr: Buffer.concat(errChunks).toString("utf8"),
          })
        }
        const timer = setTimeout(() => {
          if (child.pid !== undefined) {
            try {
              process.kill(-child.pid, "SIGKILL")
            } catch {
              child.kill("SIGKILL")
            }
          } else {
            child.kill("SIGKILL")
          }
          cleanupOrphanSlirp4netns()
        }, opts.timeoutMs)
        child.on("close", (code) => {
          cleanupOrphanSlirp4netns()
          finish(code ?? 1)
        })
        child.on("error", (err) => {
          cleanupOrphanSlirp4netns()
          if (settled) return
          settled = true
          clearTimeout(timer)
          resolvePromise({
            code: 1,
            stdout: Buffer.concat(outChunks).toString("utf8"),
            stderr: err.message,
          })
        })
      })
    },
  }
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

  const quotaBytes = resolveSandboxFileQuotaBytes(process.env)
  const execArgv = wrapWithFileSizeLimit([bwrap, ...args], quotaBytes)
  const execProgram = execArgv[0] ?? bwrap
  const execProgramArgs = execArgv.slice(1)

  const spawnEnv: NodeJS.ProcessEnv = {
    PATH: process.env["PATH"] ?? "/usr/bin:/bin",
    ...(input.childEnv ?? {}),
  }

  try {
    const result = await runner.spawn(execProgram, execProgramArgs, {
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
