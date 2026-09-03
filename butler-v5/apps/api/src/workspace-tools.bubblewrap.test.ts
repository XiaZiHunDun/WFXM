/**
 * Integration: run_command under bubblewrap (requires bwrap + distro python3 in /usr).
 * Skips when bwrap is missing (CI without bubblewrap).
 */
import { execFileSync } from "node:child_process"
import { mkdtempSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { runWithSideEffectContext } from "@butler/runtime/sandbox/index.js"
import { runTool } from "@butler/runtime/tool-runtime.js"
import { makeRunCommandTool } from "./workspace-tools.js"

const probeUrl = "http://127.0.0.1:3000/healthz"

function isBwrapAvailable(): boolean {
  const candidates = ["bwrap", "/usr/bin/bwrap"]
  const pathEnv = process.env["PATH"] ?? "/usr/bin:/bin"
  for (const bin of candidates) {
    try {
      execFileSync(bin, ["--version"], { env: { PATH: pathEnv } })
      return true
    } catch {
      // try next candidate
    }
  }
  return false
}

const bwrapAvailable = isBwrapAvailable()
// slirp egress integration is slow (cold start can exceed 60s) and requires a
// full rootless-netns + slirp4netns environment. Skip by default; enable only
// on a host explicitly provisioned for it via BUTLER_V5_TEST_FULL_SANDBOX=1.
const slirpReady = process.env["BUTLER_V5_TEST_FULL_SANDBOX"] === "1"

/**
 * Probe the loopback /healthz endpoint SYNCHRONOUSLY at collection time.
 * `it.skipIf(!healthzUp)` is evaluated when the test case is declared, before
 * any async `beforeAll` runs; an async probe would therefore always record
 * `false` and the network-allow loopback test would never execute even when a
 * real server is up. Spawning a throwaway `node -e` keeps the probe blocking
 * but bounded (2s timeout) so the skip decision is correct.
 */
function probeHealthz(): boolean {
  const script =
    `fetch(${JSON.stringify(probeUrl)},{signal:AbortSignal.timeout(2000)})` +
    `.then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))`
  try {
    execFileSync(process.execPath, ["-e", script], { timeout: 5000 })
    return true
  } catch {
    return false
  }
}

const healthzUp = bwrapAvailable && probeHealthz()

describe.skipIf(!bwrapAvailable)("makeRunCommandTool under bubblewrap", () => {
  let root: string
  let prevSandbox: string | undefined

  beforeEach(() => {
    root = mkdtempSync(join(tmpdir(), "ws-bwrap-"))
    prevSandbox = process.env["BUTLER_V5_SANDBOX"]
    process.env["BUTLER_V5_SANDBOX"] = "bubblewrap"
  })

  afterEach(() => {
    if (root) rmSync(root, { recursive: true, force: true })
    if (prevSandbox === undefined) delete process.env["BUTLER_V5_SANDBOX"]
    else process.env["BUTLER_V5_SANDBOX"] = prevSandbox
    delete process.env["BUTLER_V5_SANDBOX_NETWORK_MODE"]
    delete process.env["BUTLER_V5_SANDBOX_EGRESS_ISOLATION"]
  })

  it("runs echo and pwd inside bwrap with network-deny profile", async () => {
    const tool = makeRunCommandTool({ workspaceRoot: root })
    await runWithSideEffectContext(
      {
        sandboxProfile: "workspace-write-network-deny",
        networkAllowlist: null,
        grantId: "g-test",
        capability: "run_command",
      },
      async () => {
        const echo = await runTool(tool, { argv: ["echo", "bwrap-ok"] }, { timeoutMs: 5000 })
        expect(echo.ok).toBe(true)
        if (echo.ok) expect(String(echo.output).trim()).toBe("bwrap-ok")

        const pwd = await runTool(tool, { argv: ["pwd"] }, { timeoutMs: 5000 })
        expect(pwd.ok).toBe(true)
        if (pwd.ok) expect(String(pwd.output).trim()).toBe(root)
      },
    )
  })

  it.runIf(slirpReady)(
    "runs python3 under allowlist+slirp Grant profile (resume path)",
    async () => {
      process.env["BUTLER_V5_SANDBOX_NETWORK_MODE"] = "allowlist"
      process.env["BUTLER_V5_SANDBOX_EGRESS_ISOLATION"] = "slirp"
      const tool = makeRunCommandTool({ workspaceRoot: root })
      await runWithSideEffectContext(
        {
          sandboxProfile: "workspace-write-network-allowlist",
          networkAllowlist: ["registry.npmjs.org:443"],
          grantId: "g-test",
          capability: "run_command",
        },
        async () => {
          const py = await runTool(
            tool,
            { argv: ["python3", "-c", "print(123)"] },
            { timeoutMs: 240_000 },
          )
          expect(py.ok).toBe(true)
          if (py.ok) expect(String(py.output).trim()).toBe("123")
        },
      )
    },
    300_000,
  )


  it("runs python3 inside bwrap (distro python via ro-bind /etc/alternatives)", async () => {
    writeFileSync(join(root, "x.txt"), "1")
    const tool = makeRunCommandTool({ workspaceRoot: root })
    await runWithSideEffectContext(
      {
        sandboxProfile: "workspace-write-network-deny",
        networkAllowlist: null,
        grantId: "g-test",
        capability: "run_command",
      },
      async () => {
        const py = await runTool(
          tool,
          { argv: ["python3", "-c", "print(42)"] },
          { timeoutMs: 8000 },
        )
        expect(py.ok).toBe(true)
        if (py.ok) expect(String(py.output).trim()).toBe("42")
      },
    )
  })

  it("blocks loopback HTTP under network-deny Grant profile", async () => {
    const tool = makeRunCommandTool({ workspaceRoot: root })
    const code = [
      "import urllib.request",
      `urllib.request.urlopen(${JSON.stringify(probeUrl)}, timeout=3)`,
    ].join("\n")
    await runWithSideEffectContext(
      {
        sandboxProfile: "workspace-write-network-deny",
        networkAllowlist: null,
        grantId: "g-test",
        capability: "run_command",
      },
      async () => {
        const net = await runTool(tool, { argv: ["python3", "-c", code] }, { timeoutMs: 8000 })
        expect(net.ok).toBe(false)
      },
    )
  })

  it.skipIf(!healthzUp)(
    "reaches loopback HTTP under network-allow Grant profile (elevateNetwork path)",
    async () => {
      const tool = makeRunCommandTool({ workspaceRoot: root })
      const code = [
        "import urllib.request",
        `urllib.request.urlopen(${JSON.stringify(probeUrl)}, timeout=3)`,
      ].join("\n")
      await runWithSideEffectContext(
        {
          sandboxProfile: "workspace-write-network-allow",
          networkAllowlist: null,
          grantId: "g-test",
          capability: "run_command",
        },
        async () => {
          const net = await runTool(tool, { argv: ["python3", "-c", code] }, { timeoutMs: 8000 })
          expect(net.ok).toBe(true)
        },
      )
    },
  )
})
