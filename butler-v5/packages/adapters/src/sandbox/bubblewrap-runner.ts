import {
  resolveSandboxNetworkMode,
  resolveSandboxEgressIsolation,
} from "@butler/domain/governance/network-allowlist.js"
import type { spawn as ChildProcessSpawn } from "node:child_process"
import { existsSync } from "node:fs"
import { dirname, join } from "node:path"
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

/**
 * bwrap 只挂载固定的系统路径（/usr、/bin、/lib…），但 node / pnpm 常由 nvm、
 * volta、corepack 或 ~/.local/bin 提供，落在这些路径之外。此时子进程里的
 * `execvp node` 会直接报 `No such file or directory`——即使 run_command 已
 * 放行该程序。
 *
 * 这里补两类只读挂载：
 *   1. 当前 node 的安装前缀（`process.execPath` 的上两级），覆盖 nvm 布局下的
 *      bin/ + lib/node_modules/（pnpm 等 shim 依赖它）；
 *   2. PATH 中确实提供 node 或 pnpm 的目录（兼容 volta / corepack / 手工安装）。
 *
 * 另外支持 `BUTLER_V5_SANDBOX_EXTRA_RO_BINDS`（冒号分隔）显式追加。所有路径
 * 都会先做存在性校验——bwrap 遇到不存在的 bind 源会直接失败。
 */
export function resolveSandboxExtraBinPaths(
  input: {
    readonly env?: Readonly<Record<string, string | undefined>>
    readonly execPath?: string
    readonly pathExists?: (path: string) => boolean
  } = {},
): readonly string[] {
  const env = input.env ?? process.env
  const execPath = input.execPath ?? process.execPath
  const exists = input.pathExists ?? existsSync
  const found = new Set<string>()

  for (const raw of (env["BUTLER_V5_SANDBOX_EXTRA_RO_BINDS"] ?? "").split(":")) {
    const path = raw.trim()
    if (path !== "") found.add(path)
  }

  // `/usr/bin/node` 的上一级是 /usr，已被系统路径覆盖，无需重复绑定。
  if (execPath.includes("/")) {
    const prefix = dirname(dirname(execPath))
    if (prefix !== "" && prefix !== "/") found.add(prefix)
  }

  for (const dir of (env["PATH"] ?? "").split(":")) {
    const path = dir.trim()
    if (path === "" || path === "/") continue
    if (exists(join(path, "node")) || exists(join(path, "pnpm"))) found.add(path)
  }

  return [...found].filter((path) => exists(path))
}

/** True when `path` is already covered by a read-only bind (prefix match on dir boundary). */
function isCoveredByReadOnlyBind(path: string, roots: readonly string[]): boolean {
  return roots.some((root) => path === root || path.startsWith(`${root}/`))
}

/**
 * 沙箱内的 HOME。挂在 bwrap 的 tmpfs 上：可写、进程退出即销毁，不落到宿主，
 * 也不会把宿主的 `~/.gitconfig` / 缓存暴露给沙箱。
 */
export const SANDBOX_HOME_DIR = "/tmp/butler-home"

/** 沙箱内的 corepack 缓存目录：宿主缓存以只读方式挂载到这里。 */
export const SANDBOX_COREPACK_HOME = `${SANDBOX_HOME_DIR}/.cache/node/corepack`

/**
 * 宿主上已缓存的 corepack 目录（含 `lastKnownGood.json` 与 `v1/<pm>/<version>`），
 * 整目录只读挂进沙箱。沙箱默认 deny 网络，没有这份缓存时 corepack 会去请求
 * registry 而失败；命中缓存即可离线运行 `pnpm`。用
 * `BUTLER_V5_SANDBOX_COREPACK_CACHE` 可显式指定目录。
 */
export function resolveSandboxCorepackSeedDir(
  input: {
    readonly env?: Readonly<Record<string, string | undefined>>
    readonly pathExists?: (path: string) => boolean
  } = {},
): string | undefined {
  const env = input.env ?? process.env
  const exists = input.pathExists ?? existsSync
  const explicit = (env["BUTLER_V5_SANDBOX_COREPACK_CACHE"] ?? "").trim()
  if (explicit !== "") return exists(explicit) ? explicit : undefined
  const home = (env["HOME"] ?? "").trim()
  if (home === "") return undefined
  const cached = join(home, ".cache/node/corepack")
  return exists(cached) ? cached : undefined
}

/**
 * 沙箱进程的 HOME 与包管理器缓存环境。corepack / node 依赖 HOME 解析
 * `os.homedir()`，缺失时会直接抛 `uv_os_homedir ENOENT`。
 */
export function resolveSandboxHomeEnv(): NodeJS.ProcessEnv {
  return {
    HOME: SANDBOX_HOME_DIR,
    XDG_CACHE_HOME: `${SANDBOX_HOME_DIR}/.cache`,
    XDG_DATA_HOME: `${SANDBOX_HOME_DIR}/.local/share`,
    COREPACK_HOME: SANDBOX_COREPACK_HOME,
    COREPACK_ENABLE_DOWNLOAD_PROMPT: "0",
  }
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
  /** R16 sandbox 扩面：readOnly → workspace bind 用 --ro-bind（read_file 用） */
  readonly options?: { readonly readOnly?: boolean; readonly shareNet?: boolean }
}

export interface BubblewrapRunResult {
  readonly ok: boolean
  readonly stdout?: string
  readonly stderr?: string
  readonly reason?: string
  /** 子进程退出码（非零时保留，供调用方区分“命令失败”与“沙箱故障”）。 */
  readonly exitCode?: number
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
  /** R16 sandbox 扩面：read_file → workspace bind 用 --ro-bind */
  readonly readOnly?: boolean
  /** R16 sandbox 扩面：write_file → stdin 透传 tee-equivalent；触发时 dispatch 到 executeWriteInSandbox */
  readonly stdinContent?: string
}): Promise<BubblewrapRunResult | { readonly ok: true; readonly mode: "disabled" }> {
  const env = input.env ?? process.env
  const injectEnv = input.injectEnv ?? {}
  if ((env["BUTLER_V5_SANDBOX"] ?? "").trim() !== "bubblewrap") {
    return { ok: true, mode: "disabled" }
  }

  // R16 sandbox 扩面：write_file dispatch — 不走 allowlist/slirp 路径（始终 DENY profile）
  if (input.stdinContent !== undefined) {
    return await executeWriteInSandbox({
      argv: input.argv,
      workspaceRoot: input.workspaceRoot,
      ...(input.profileName !== undefined ? { profileName: input.profileName } : {}),
      stdinContent: input.stdinContent,
      env,
      ...(input.bwrapPath ? { bwrapPath: input.bwrapPath } : {}),
    })
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
          ...resolveSandboxHomeEnv(),
          ...buildSandboxProxyEnv(`http://${SLIRP_HOST_GATEWAY}:${proxyPort}`),
          ...injectEnv,
        }
      } else {
        proxyHandle = await startEgressAllowlistProxy(input.networkAllowlist, { env })
        childEnv = {
          PATH: env["PATH"] ?? "/usr/bin:/bin:/usr/sbin:/sbin",
          ...resolveSandboxHomeEnv(),
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
        ...resolveSandboxHomeEnv(),
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
      ...(input.readOnly !== undefined ? { options: { readOnly: input.readOnly } } : {}),
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
export async function preflightBubblewrap(bwrapPath = "bwrap"): Promise<BubblewrapPreflightResult> {
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
  options: {
    readonly shareNet?: boolean
    readonly readOnly?: boolean
    /** 覆盖自动探测的额外只读路径（测试注入用）。 */
    readonly extraBinPaths?: readonly string[]
    /** 覆盖自动探测的 corepack pnpm 缓存种子；传 null 表示不挂载（测试注入用）。 */
    readonly corepackSeedDir?: string | null
  } = {},
): string[] {
  const args = ["--die-with-parent"]
  // 最小 /dev（含 /dev/null）：git 等命令会打开 /dev/null，缺了会直接报
  // "could not open '/dev/null'"，把 run_command 变成不可用。
  args.push("--dev", "/dev")
  if (options.shareNet) {
    args.push("--share-net")
  } else if (profile.network === "deny") {
    args.push("--unshare-net")
  }
  args.push("--tmpfs", "/tmp")
  // 可写 HOME：corepack / node 调用 os.homedir() 时不再 ENOENT；tmpfs 随进程销毁。
  args.push("--dir", SANDBOX_HOME_DIR)
  const corepackSeed =
    options.corepackSeedDir !== undefined
      ? options.corepackSeedDir
      : (resolveSandboxCorepackSeedDir() ?? null)
  if (corepackSeed !== null && corepackSeed !== "") {
    args.push("--ro-bind", corepackSeed, SANDBOX_COREPACK_HOME)
  }
  // R16 sandbox 扩面：read_file 用 --ro-bind（readOnly=true）防意外写；write_file 维持 --bind
  args.push(options.readOnly ? "--ro-bind" : "--bind", profile.workspaceRoot, profile.workspaceRoot)
  const binds = [...profile.readOnlySystemPaths]
  const extraBinPaths = options.extraBinPaths ?? resolveSandboxExtraBinPaths()
  for (const path of extraBinPaths) {
    if (!isCoveredByReadOnlyBind(path, binds)) binds.push(path)
  }
  for (const path of binds) {
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
  const args = buildBubblewrapArgs(input.profile, input.argv, input.options ?? {})
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
    ...resolveSandboxHomeEnv(),
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
      return {
        ok: false,
        stderr: result.stderr,
        reason: result.stderr || `exit ${result.code}`,
        exitCode: result.code,
      }
    }
    return { ok: true, stdout: result.stdout, stderr: result.stderr }
  } catch (err) {
    return {
      ok: false,
      reason: err instanceof Error ? err.message : String(err),
    }
  }
}

/**
 * R16 sandbox 扩面：write_file 走 bwrap tee-equivalent 的入口。
 *
 * 与 `runInBubblewrap` 的差异：(1) `stdio: ["pipe", "pipe", "pipe"]` 让 stdin
 * 透传 host 内容（tee 写文件）；(2) inline `child_process.spawn` 不走
 * `ProcessRunner` 抽象（`createDefaultProcessRunner:336` 用 stdio:["ignore",...]
 * 关 stdin）；(3) `argv[0]` 不带 `/` 的 cat/tee-equivalent（`ALLOWED_RUN_COMMANDS`
 * 类）。
 *
 * 注：本 helper 故意不接 slirp/allowlist proxy 路径——write_file 总是 DENY
 * profile（`profiles.ts:54` ceiling），不走 `executeArgvInSandbox:144-156` 的
 * allowlist 分支。如未来 write_file 被允许 allowlist，须补走
 * `executeArgvInSandbox` 的 slirp 路径。
 */
export async function executeWriteInSandbox(input: {
  readonly argv: readonly string[]
  readonly workspaceRoot: string
  readonly profileName?: string | null
  readonly stdinContent: string
  readonly env?: NodeJS.ProcessEnv
  readonly bwrapPath?: string
  /** 测试注入；默认 `node:child_process.spawn`。 */
  readonly spawnFn?: typeof ChildProcessSpawn
}): Promise<BubblewrapRunResult> {
  if (input.argv.length === 0) {
    return { ok: false, reason: "argv must not be empty" }
  }
  if (input.argv[0]?.includes("/")) {
    return { ok: false, reason: "shell-style command paths are not allowed" }
  }

  const env = input.env ?? process.env
  const profile = resolveSandboxProfile({
    workspaceRoot: input.workspaceRoot,
    ...(input.profileName !== undefined ? { profileName: input.profileName } : {}),
  })

  const bwrap = input.bwrapPath ?? "bwrap"
  const args = buildBubblewrapArgs(profile, input.argv, { readOnly: false })
  const quotaBytes = resolveSandboxFileQuotaBytes(env)
  const execArgv = wrapWithFileSizeLimit([bwrap, ...args], quotaBytes)
  const execProgram = execArgv[0] ?? bwrap
  const execProgramArgs = execArgv.slice(1)

  const spawnEnv: NodeJS.ProcessEnv = {
    PATH: env["PATH"] ?? "/usr/bin:/bin",
    ...resolveSandboxHomeEnv(),
  }

  const spawnImpl = input.spawnFn ?? (await import("node:child_process")).spawn

  return await new Promise((resolvePromise) => {
    let settled = false
    const outChunks: Buffer[] = []
    const errChunks: Buffer[] = []
    let outTotal = 0
    let errTotal = 0
    let child: ReturnType<typeof spawnImpl>
    try {
      child = spawnImpl(execProgram, [...execProgramArgs], {
        cwd: profile.workspaceRoot,
        env: spawnEnv,
        stdio: ["pipe", "pipe", "pipe"],
        detached: true,
      })
    } catch (err) {
      resolvePromise({
        ok: false,
        reason: err instanceof Error ? err.message : String(err),
      })
      return
    }

    const takeOut = (buf: Buffer) => {
      outTotal += buf.length
      if (outTotal <= profile.maxOutputBytes) outChunks.push(buf)
    }
    const takeErr = (buf: Buffer) => {
      errTotal += buf.length
      if (errTotal <= profile.maxOutputBytes) errChunks.push(buf)
    }
    child.stdout?.on("data", (b: Buffer) => takeOut(b))
    child.stderr?.on("data", (b: Buffer) => takeErr(b))
    const finish = (code: number) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      const stdout = Buffer.concat(outChunks).toString("utf8")
      const stderr = Buffer.concat(errChunks).toString("utf8")
      if (code !== 0) {
        resolvePromise({ ok: false, stderr, reason: stderr || `exit ${code}` })
        return
      }
      resolvePromise({ ok: true, stdout, stderr })
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
    }, profile.timeoutMs)
    child.on("close", (code) => finish(code ?? 1))
    child.on("error", (err) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      const stderr = Buffer.concat(errChunks).toString("utf8")
      resolvePromise({ ok: false, stderr, reason: err.message })
    })

    try {
      child.stdin?.write(input.stdinContent)
      child.stdin?.end()
    } catch {
      // error already wired via 'error' event
    }
  })
}
