export interface SandboxProfile {
  readonly name: string
  readonly workspaceRoot: string
  readonly network: "deny" | "allow"
  readonly readOnlySystemPaths: readonly string[]
  readonly maxOutputBytes: number
  readonly timeoutMs: number
}

export const DEFAULT_SANDBOX_PROFILE: SandboxProfile = {
  name: "workspace-write-network-deny",
  workspaceRoot: process.cwd(),
  network: "deny",
  readOnlySystemPaths: ["/usr", "/bin", "/lib", "/lib64"],
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
    },
  ) => Promise<{ readonly code: number; readonly stdout: string; readonly stderr: string }>
}

export interface BubblewrapRunInput {
  readonly argv: readonly string[]
  readonly profile: SandboxProfile
  readonly runner?: ProcessRunner
  readonly bwrapPath?: string
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

export function buildBubblewrapArgs(profile: SandboxProfile, argv: readonly string[]): string[] {
  const args = [
    "--die-with-parent",
    "--unshare-net",
    "--tmpfs",
    "/tmp",
    "--bind",
    profile.workspaceRoot,
    profile.workspaceRoot,
  ]
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

  try {
    const result = await runner.spawn(bwrap, args, {
      cwd: input.profile.workspaceRoot,
      timeoutMs: input.profile.timeoutMs,
      maxOutputBytes: input.profile.maxOutputBytes,
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
