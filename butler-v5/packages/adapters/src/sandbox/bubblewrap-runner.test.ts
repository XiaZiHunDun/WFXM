import { describe, expect, it, vi } from "vitest"
import {
  buildBubblewrapArgs,
  DEFAULT_SANDBOX_PROFILE,
  executeArgvInSandbox,
  preflightBubblewrap,
  resolveSandboxProfile,
  runInBubblewrap,
  type ProcessRunner,
} from "./bubblewrap-runner.js"

describe("bubblewrap runner", () => {
  it("builds fail-closed argv with workspace bind and network deny", () => {
    const args = buildBubblewrapArgs(DEFAULT_SANDBOX_PROFILE, ["echo", "hi"])
    expect(args).toContain("--unshare-net")
    expect(args).toContain("--bind")
    expect(DEFAULT_SANDBOX_PROFILE.readOnlySystemPaths).toContain("/etc/alternatives")
    expect(DEFAULT_SANDBOX_PROFILE.readOnlySystemPaths).toContain("/etc/ssl")
    expect(args.at(-2)).toBe("echo")
    expect(args.at(-1)).toBe("hi")
  })

  it("omits --unshare-net for network-allow profile", () => {
    const profile = resolveSandboxProfile({
      workspaceRoot: "/tmp/ws",
      profileName: "workspace-write-network-allow",
    })
    const args = buildBubblewrapArgs(profile, ["echo", "hi"])
    expect(args).not.toContain("--unshare-net")
    expect(profile.network).toBe("allow")
  })

  it("executeArgvInSandbox returns disabled when env unset", async () => {
    const result = await executeArgvInSandbox({
      argv: ["echo", "hi"],
      workspaceRoot: "/tmp/ws",
      env: {},
    })
    expect(result).toEqual({ ok: true, mode: "disabled" })
  })

  it("omits --unshare-net for network-allowlist profile", () => {
    const profile = resolveSandboxProfile({
      workspaceRoot: "/tmp/ws",
      profileName: "workspace-write-network-allowlist",
    })
    const args = buildBubblewrapArgs(profile, ["echo", "hi"])
    expect(args).not.toContain("--unshare-net")
    expect(profile.network).toBe("allowlist")
  })

  it("fail-closed allowlist profile when network mode is binary", async () => {
    const result = await executeArgvInSandbox({
      argv: ["echo", "hi"],
      workspaceRoot: "/tmp/ws",
      profileName: "workspace-write-network-allowlist",
      networkAllowlist: ["registry.npmjs.org:443"],
      env: { BUTLER_V5_SANDBOX: "bubblewrap", BUTLER_V5_SANDBOX_NETWORK_MODE: "binary" },
    })
    expect(result.ok).toBe(false)
    if (result.ok || "mode" in result) return
    expect(result.reason).toMatch(/SANDBOX_NETWORK_MODE=allowlist/)
  })

  it("starts egress proxy env for allowlist profile", async () => {
    const runner: ProcessRunner = {
      spawn: vi.fn(async (_cmd, args, opts) => {
        expect(args).not.toContain("--unshare-net")
        expect(opts.env?.["HTTPS_PROXY"]).toMatch(/^http:\/\/127\.0\.0\.1:/)
        return { code: 0, stdout: "ok\n", stderr: "" }
      }),
    }
    const result = await executeArgvInSandbox({
      argv: ["echo", "hi"],
      workspaceRoot: "/tmp/ws",
      profileName: "workspace-write-network-allowlist",
      networkAllowlist: ["registry.npmjs.org:443"],
      env: {
        BUTLER_V5_SANDBOX: "bubblewrap",
        BUTLER_V5_SANDBOX_NETWORK_MODE: "allowlist",
      },
      runner,
    })
    expect(result.ok).toBe(true)
  })

  it("slirp isolation spawns unshare and uses host gateway proxy", async () => {
    const runner: ProcessRunner = {
      spawn: vi.fn(async (cmd, _args, opts) => {
        if (cmd === "unshare") {
          if (opts.env?.["HTTPS_PROXY"]) {
            expect(opts.env["HTTPS_PROXY"]).toMatch(/^http:\/\/10\.0\.2\.2:/)
          }
          return { code: 0, stdout: "ok\n", stderr: "" }
        }
        return { code: 0, stdout: "ok\n", stderr: "" }
      }),
    }
    const result = await executeArgvInSandbox({
      argv: ["echo", "hi"],
      workspaceRoot: "/tmp/ws",
      profileName: "workspace-write-network-allowlist",
      networkAllowlist: ["registry.npmjs.org:443"],
      env: {
        BUTLER_V5_SANDBOX: "bubblewrap",
        BUTLER_V5_SANDBOX_NETWORK_MODE: "allowlist",
        BUTLER_V5_SANDBOX_EGRESS_ISOLATION: "slirp",
      },
      runner,
    })
    expect(result.ok).toBe(true)
    expect(runner.spawn).toHaveBeenCalledWith(
      "unshare",
      expect.arrayContaining(["-U", "-r", "-n"]),
      expect.any(Object),
    )
  })

  it("executeArgvInSandbox uses Grant profile name under bubblewrap", async () => {
    const runner: ProcessRunner = {
      spawn: vi.fn(async (_cmd, args) => {
        expect(args).not.toContain("--unshare-net")
        return { code: 0, stdout: "ok\n", stderr: "" }
      }),
    }
    const result = await executeArgvInSandbox({
      argv: ["echo", "hi"],
      workspaceRoot: "/tmp/ws",
      profileName: "workspace-write-network-allow",
      env: { BUTLER_V5_SANDBOX: "bubblewrap" },
      runner,
    })
    expect(result.ok).toBe(true)
    if (result.ok && !("mode" in result)) {
      expect(result.stdout).toBe("ok\n")
    }
  })

  it("fail-closed when no process runner is available", async () => {
    const result = await runInBubblewrap({
      argv: ["echo", "hi"],
      profile: DEFAULT_SANDBOX_PROFILE,
    })
    expect(result.ok).toBe(false)
    expect(result.reason).toMatch(/fail-closed/i)
  })

  it("executes through an injected process runner", async () => {
    const runner: ProcessRunner = {
      spawn: vi.fn(async () => ({ code: 0, stdout: "hi\n", stderr: "" })),
    }
    const result = await runInBubblewrap({
      argv: ["echo", "hi"],
      profile: DEFAULT_SANDBOX_PROFILE,
      runner,
    })
    expect(result).toEqual({ ok: true, stdout: "hi\n", stderr: "" })
  })

  it("preflightBubblewrap reports missing bwrap", async () => {
    const result = await preflightBubblewrap("/nonexistent/bwrap-binary")
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.reason).toMatch(/preflight failed/i)
    }
  })
})
