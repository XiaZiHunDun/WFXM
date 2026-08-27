import {
  createDefaultProcessRunner,
  executeArgvInSandbox,
  type BubblewrapRunResult,
  type ProcessRunner,
} from "./bubblewrap-runner.js"

export { createDefaultProcessRunner } from "./bubblewrap-runner.js"
import { createServer } from "node:http"

const DEFAULT_PROBE_URL = "http://127.0.0.1:3000/healthz"

/** Use bare `python3` once `/etc/alternatives` is ro-bound in the sandbox profile. */
function networkProbeArgv(probeUrl: string): readonly string[] {
  const code = [
    "import urllib.request",
    `urllib.request.urlopen(${JSON.stringify(probeUrl)}, timeout=3)`,
  ].join("\n")
  return ["python3", "-c", code]
}

function isDisabled(
  result: BubblewrapRunResult | { readonly ok: true; readonly mode: "disabled" },
): result is { readonly ok: true; readonly mode: "disabled" } {
  return result.ok && "mode" in result && result.mode === "disabled"
}

export interface SandboxNetworkProbeResult {
  readonly ok: boolean
  readonly sandboxEnabled: boolean
  readonly denyBlockedNetwork: boolean
  readonly allowReachedNetwork: boolean
  readonly probeUrl: string
  readonly reason?: string
}

/**
 * Production point-check: network-deny profile blocks loopback HTTP;
 * network-allow profile can reach the same URL (Grant `elevateNetwork` path).
 */
export async function probeSandboxNetworkIsolation(args: {
  readonly workspaceRoot: string
  readonly env?: NodeJS.ProcessEnv
  readonly runner: ProcessRunner
  readonly probeUrl?: string
}): Promise<SandboxNetworkProbeResult> {
  const env = args.env ?? process.env
  const probeUrl = (args.probeUrl ?? DEFAULT_PROBE_URL).trim() || DEFAULT_PROBE_URL
  const argv = networkProbeArgv(probeUrl)
  const base = {
    argv,
    workspaceRoot: args.workspaceRoot,
    env,
    runner: args.runner,
  }

  const denyResult = await executeArgvInSandbox({
    ...base,
    profileName: "workspace-write-network-deny",
  })
  if (isDisabled(denyResult)) {
    return {
      ok: false,
      sandboxEnabled: false,
      denyBlockedNetwork: false,
      allowReachedNetwork: false,
      probeUrl,
      reason: "BUTLER_V5_SANDBOX is not bubblewrap",
    }
  }
  const denyBlockedNetwork = !denyResult.ok

  const allowResult = await executeArgvInSandbox({
    ...base,
    profileName: "workspace-write-network-allow",
  })
  if (isDisabled(allowResult)) {
    return {
      ok: false,
      sandboxEnabled: false,
      denyBlockedNetwork,
      allowReachedNetwork: false,
      probeUrl,
      reason: "BUTLER_V5_SANDBOX is not bubblewrap",
    }
  }
  const allowReachedNetwork = allowResult.ok

  const ok = denyBlockedNetwork && allowReachedNetwork
  return {
    ok,
    sandboxEnabled: true,
    denyBlockedNetwork,
    allowReachedNetwork,
    probeUrl,
    ...(!ok
      ? {
          reason: !denyBlockedNetwork
            ? "network-deny profile did not block probe (expected fail-closed)"
            : "network-allow profile could not reach probe URL",
        }
      : {}),
  }
}

export interface SandboxAllowlistProbeResult {
  readonly ok: boolean
  readonly allowedReachable: boolean
  readonly blockedReachable: boolean
  readonly allowedUrl: string
  readonly blockedUrl: string
  readonly reason?: string
}

/** P2c: verify allowlist Grant reaches allowed host and blocks other host via egress proxy. */
export async function probeSandboxAllowlistEgress(args: {
  readonly workspaceRoot: string
  readonly env?: NodeJS.ProcessEnv
  readonly runner: ProcessRunner
}): Promise<SandboxAllowlistProbeResult> {
  const env = {
    ...(args.env ?? process.env),
    BUTLER_V5_SANDBOX: "bubblewrap",
    BUTLER_V5_SANDBOX_NETWORK_MODE: "allowlist",
    BUTLER_V5_SANDBOX_EGRESS_ISOLATION: "proxy",
    BUTLER_V5_SANDBOX_ALLOW_PRIVATE_EGRESS: "1",
  }

  const allowedServer = createServer((_req, res) => {
    res.writeHead(200)
    res.end("allowlist-ok")
  })
  const blockedServer = createServer((_req, res) => {
    res.writeHead(200)
    res.end("blocked-should-not-see")
  })

  await new Promise<void>((resolve) => allowedServer.listen(0, "127.0.0.1", () => resolve()))
  await new Promise<void>((resolve) => blockedServer.listen(0, "127.0.0.1", () => resolve()))

  const allowedAddr = allowedServer.address()
  const blockedAddr = blockedServer.address()
  const allowedPort = typeof allowedAddr === "object" && allowedAddr ? allowedAddr.port : 0
  const blockedPort = typeof blockedAddr === "object" && blockedAddr ? blockedAddr.port : 0
  const allowedUrl = `http://127.0.0.1:${allowedPort}/`
  const blockedUrl = `http://127.0.0.1:${blockedPort}/`

  const code = (url: string) =>
    [
      "import urllib.request",
      `print(urllib.request.urlopen(${JSON.stringify(url)}, timeout=3).read().decode())`,
    ].join("\n")

  try {
    const allowedResult = await executeArgvInSandbox({
      argv: ["python3", "-c", code(allowedUrl)],
      workspaceRoot: args.workspaceRoot,
      profileName: "workspace-write-network-allowlist",
      networkAllowlist: [`127.0.0.1:${allowedPort}`],
      env,
      runner: args.runner,
    })
    const blockedResult = await executeArgvInSandbox({
      argv: ["python3", "-c", code(blockedUrl)],
      workspaceRoot: args.workspaceRoot,
      profileName: "workspace-write-network-allowlist",
      networkAllowlist: [`127.0.0.1:${allowedPort}`],
      env,
      runner: args.runner,
    })

    const allowedReachable =
      allowedResult.ok &&
      !("mode" in allowedResult) &&
      allowedResult.stdout?.includes("allowlist-ok")
    const blockedReachable =
      blockedResult.ok && !("mode" in blockedResult) && blockedResult.stdout?.includes("blocked")

    const ok = Boolean(allowedReachable) && !blockedReachable
    return {
      ok,
      allowedReachable: Boolean(allowedReachable),
      blockedReachable: Boolean(blockedReachable),
      allowedUrl,
      blockedUrl,
      ...(!ok
        ? {
            reason: !allowedReachable
              ? "allowlisted host unreachable through egress proxy"
              : "non-allowlisted host was reachable (fail-open)",
          }
        : {}),
    }
  } finally {
    await new Promise<void>((resolve) => allowedServer.close(() => resolve()))
    await new Promise<void>((resolve) => blockedServer.close(() => resolve()))
  }
}

const REGISTRY_ALLOWLIST_ENTRY = "registry.npmjs.org:443"
const REGISTRY_PROBE_URL = "https://registry.npmjs.org/left-pad"

/** Live npm registry HTTPS fetch through allowlist egress (production point-check). */
export async function probeAllowlistPnpmRegistry(args: {
  readonly workspaceRoot: string
  readonly env?: NodeJS.ProcessEnv
  readonly runner?: ProcessRunner
}): Promise<{ readonly ok: boolean; readonly reason?: string; readonly output?: string }> {
  const env = {
    ...(args.env ?? process.env),
    BUTLER_V5_SANDBOX: "bubblewrap",
    BUTLER_V5_SANDBOX_NETWORK_MODE: "allowlist",
    // Live registry probe uses egress proxy path (P2c); slirp raw path is covered by probeSandboxAllowlistSlirpIsolation.
    BUTLER_V5_SANDBOX_EGRESS_ISOLATION: "proxy",
  }
  const runner = args.runner ?? createDefaultProcessRunner()

  const code = [
    "import urllib.request",
    `r = urllib.request.urlopen(${JSON.stringify(REGISTRY_PROBE_URL)}, timeout=15)`,
    "body = r.read(4096).decode('utf-8', errors='replace')",
    "print(r.status, body[:120])",
  ].join("\n")

  const result = await executeArgvInSandbox({
    argv: ["python3", "-c", code],
    workspaceRoot: args.workspaceRoot,
    profileName: "workspace-write-network-allowlist",
    networkAllowlist: [REGISTRY_ALLOWLIST_ENTRY],
    env,
    runner,
  })

  if (isDisabled(result)) {
    return { ok: false, reason: "sandbox disabled" }
  }
  if (!result.ok) {
    const detail = [result.reason, result.stderr, result.stdout].filter(Boolean).join(" | ")
    return { ok: false, reason: detail || "registry probe failed under allowlist" }
  }
  const output = (result.stdout ?? "").trim()
  if (!output.startsWith("200")) {
    return { ok: false, reason: output || "registry probe did not return HTTP 200" }
  }
  return { ok: true, output }
}

export interface SandboxSlirpProbeResult {
  readonly ok: boolean
  readonly rawSocketBlocked: boolean
  readonly proxyPathReachable: boolean
  readonly reason?: string
}

const SLIRP_PROBE_LOCAL_PORT = 37653

/** P2d: raw TCP blocked; allowlisted loopback reachable inside slirp netns. */
export async function probeSandboxAllowlistSlirpIsolation(args: {
  readonly workspaceRoot: string
  readonly env?: NodeJS.ProcessEnv
  readonly runner: ProcessRunner
}): Promise<SandboxSlirpProbeResult> {
  const env = {
    ...(args.env ?? process.env),
    BUTLER_V5_SANDBOX: "bubblewrap",
    BUTLER_V5_SANDBOX_NETWORK_MODE: "allowlist",
    BUTLER_V5_SANDBOX_EGRESS_ISOLATION: "slirp",
    BUTLER_V5_SANDBOX_ALLOW_PRIVATE_EGRESS: "1",
  }

  const allowlist = [`127.0.0.1:${SLIRP_PROBE_LOCAL_PORT}`]

  const rawProbe = [
    "import socket",
    "try:",
    '  socket.create_connection(("8.8.8.8", 443), timeout=2)',
    '  print("raw-open")',
    "except OSError:",
    '  print("raw-blocked")',
  ].join("\n")

  const localProbe = [
    "import socket, threading, time",
    `PORT = ${SLIRP_PROBE_LOCAL_PORT}`,
    "def serve():",
    "  s = socket.socket()",
    "  s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)",
    "  s.bind(('127.0.0.1', PORT))",
    "  s.listen(1)",
    "  conn, _ = s.accept()",
    "  conn.send(b'slirp-allow-ok')",
    "  conn.close()",
    "threading.Thread(target=serve, daemon=True).start()",
    "time.sleep(0.5)",
    "c = socket.create_connection(('127.0.0.1', PORT), timeout=3)",
    "print(c.recv(32).decode())",
  ].join("\n")

  const rawResult = await executeArgvInSandbox({
    argv: ["python3", "-c", rawProbe],
    workspaceRoot: args.workspaceRoot,
    profileName: "workspace-write-network-allowlist",
    networkAllowlist: allowlist,
    env,
    runner: args.runner,
  })
  const localResult = await executeArgvInSandbox({
    argv: ["python3", "-c", localProbe],
    workspaceRoot: args.workspaceRoot,
    profileName: "workspace-write-network-allowlist",
    networkAllowlist: allowlist,
    env,
    runner: args.runner,
  })

  const rawDisabled = "mode" in rawResult
  const rawOut = rawDisabled ? "" : (rawResult.stdout ?? "")
  const rawProbeRan = rawOut.includes("raw-open") || rawOut.includes("raw-blocked")
  // Sandbox failed to launch (no "raw-open"/"raw-blocked" scribble in stdout, e.g.
  // rootless unshare denied on /proc/*/uid_map): no command executed, hence no
  // egress possible → treated as blocked (safe), NOT as a raw-socket fail-open.
  const slirpUnavailable = !rawDisabled && !rawProbeRan
  const rawSocketBlocked =
    slirpUnavailable || (rawOut.includes("raw-blocked") && !rawOut.includes("raw-open"))
  const proxyPathReachable =
    localResult.ok &&
    !("mode" in localResult) &&
    (localResult.stdout?.includes("slirp-allow-ok") ?? false)

  const ok = rawSocketBlocked && proxyPathReachable
  return {
    ok,
    rawSocketBlocked,
    proxyPathReachable,
    ...(!ok
      ? {
          reason: slirpUnavailable
            ? rawResult.reason || "slirp sandbox failed to launch (fail-closed, no egress)"
            : !rawSocketBlocked
              ? "raw socket reached non-allowlisted host (P2d fail-open)"
              : "allowlisted loopback unreachable inside slirp netns",
        }
      : {}),
  }
}
