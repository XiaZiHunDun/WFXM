import { describe, expect, it, vi } from "vitest"
import type { spawn as ChildProcessSpawn } from "node:child_process"
import {
  buildBubblewrapArgs,
  DEFAULT_SANDBOX_PROFILE,
  executeArgvInSandbox,
  executeWriteInSandbox,
  preflightBubblewrap,
  resolveSandboxFileQuotaBytes,
  resolveSandboxProfile,
  runInBubblewrap,
  wrapWithFileSizeLimit,
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

  it("falls back to proxy allowlist when slirp fails and SLIRP_FALLBACK enabled", async () => {
    let unshareCalls = 0
    const runner: ProcessRunner = {
      spawn: vi.fn(async (cmd, _args, opts) => {
        if (cmd === "unshare") {
          unshareCalls += 1
          if (unshareCalls === 1) return { code: 0, stdout: "", stderr: "" }
          return { code: 1, stdout: "", stderr: "iptables setup failed" }
        }
        if (cmd === "bwrap") {
          expect(opts.env?.["HTTPS_PROXY"]).toMatch(/^http:\/\/127\.0\.0\.1:/)
          return { code: 0, stdout: "fallback-ok\n", stderr: "" }
        }
        return { code: 0, stdout: "ok\n", stderr: "" }
      }),
    }
    const result = await executeArgvInSandbox({
      argv: ["echo", "fallback-ok"],
      workspaceRoot: "/tmp/ws",
      profileName: "workspace-write-network-allowlist",
      networkAllowlist: ["registry.npmjs.org:443"],
      env: {
        BUTLER_V5_SANDBOX: "bubblewrap",
        BUTLER_V5_SANDBOX_NETWORK_MODE: "allowlist",
        BUTLER_V5_SANDBOX_EGRESS_ISOLATION: "slirp",
        BUTLER_V5_SANDBOX_SLIRP_FALLBACK: "1",
      },
      runner,
    })
    expect(result.ok).toBe(true)
    if (result.ok && !("mode" in result)) {
      expect(String(result.stdout)).toContain("fallback-ok")
    }
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

  it("resolveSandboxFileQuotaBytes ignores unset/zero/invalid", () => {
    expect(resolveSandboxFileQuotaBytes({})).toBeNull()
    expect(resolveSandboxFileQuotaBytes({ BUTLER_V5_SANDBOX_MAX_FILE_BYTES: "" })).toBeNull()
    expect(resolveSandboxFileQuotaBytes({ BUTLER_V5_SANDBOX_MAX_FILE_BYTES: "0" })).toBeNull()
    expect(resolveSandboxFileQuotaBytes({ BUTLER_V5_SANDBOX_MAX_FILE_BYTES: "-1" })).toBeNull()
    expect(resolveSandboxFileQuotaBytes({ BUTLER_V5_SANDBOX_MAX_FILE_BYTES: "abc" })).toBeNull()
  })

  it("resolveSandboxFileQuotaBytes returns a positive cap", () => {
    expect(
      resolveSandboxFileQuotaBytes({ BUTLER_V5_SANDBOX_MAX_FILE_BYTES: "8388608" }),
    ).toBe(8388608)
  })

  it("wrapWithFileSizeLimit prefixes prlimit only when capped", () => {
    expect(wrapWithFileSizeLimit(["bwrap", "--", "echo"], 1048576)).toEqual([
      "prlimit",
      "--fsize=1048576:1048576",
      "--",
      "bwrap",
      "--",
      "echo",
    ])
    expect(wrapWithFileSizeLimit(["bwrap", "--", "echo"], null)).toEqual([
      "bwrap",
      "--",
      "echo",
    ])
  })

  it("runInBubblewrap wraps bwrap with prlimit when quota is set", async () => {
    const runner: ProcessRunner = {
      spawn: vi.fn(async () => ({ code: 0, stdout: "ok\n", stderr: "" })),
    }
    process.env["BUTLER_V5_SANDBOX_MAX_FILE_BYTES"] = "1048576"
    try {
      const result = await runInBubblewrap({
        argv: ["echo", "hi"],
        profile: DEFAULT_SANDBOX_PROFILE,
        runner,
      })
      expect(result.ok).toBe(true)
      const call = (runner.spawn as ReturnType<typeof vi.fn>).mock.calls[0] ?? []
      const program = call[0]
      const argv = call[1] as readonly string[]
      expect(program).toBe("prlimit")
      expect(argv[0]).toContain("--fsize=1048576:1048576")
      expect(argv[1]).toBe("--")
      expect(argv[2]).toBe("bwrap")
    } finally {
      delete process.env["BUTLER_V5_SANDBOX_MAX_FILE_BYTES"]
    }
  })

  it("buildBubblewrapArgs readOnly=true uses --ro-bind for workspace (R16)", () => {
    const args = buildBubblewrapArgs(DEFAULT_SANDBOX_PROFILE, ["cat", "--", "x.txt"], {
      readOnly: true,
    })
    // workspaceRoot 后面两个连续出现 --ro-bind 后跟 ws
    const roIdx = args.indexOf("--ro-bind")
    expect(roIdx).toBeGreaterThanOrEqual(0)
    // 紧跟 ro-bind 后是 workspaceRoot（不带 --bind 副作用）
    expect(args[roIdx + 1]).toBe(DEFAULT_SANDBOX_PROFILE.workspaceRoot)
    expect(args[roIdx + 2]).toBe(DEFAULT_SANDBOX_PROFILE.workspaceRoot)
    expect(args).not.toContain("--bind")
  })

  it("buildBubblewrapArgs readOnly defaults to false (--bind)", () => {
    const args = buildBubblewrapArgs(DEFAULT_SANDBOX_PROFILE, ["tee", "x.txt"])
    expect(args).toContain("--bind")
    // verify workspaceRoot 紧跟 --bind
    const bindIdx = args.indexOf("--bind")
    expect(args[bindIdx + 1]).toBe(DEFAULT_SANDBOX_PROFILE.workspaceRoot)
  })

  it("executeArgvInSandbox readOnly=true passes options to runInBubblewrap (R16)", async () => {
    const runner: ProcessRunner = {
      spawn: vi.fn(async (_cmd, args) => {
        expect(args).toContain("--ro-bind")
        return { code: 0, stdout: "ok\n", stderr: "" }
      }),
    }
    const result = await executeArgvInSandbox({
      argv: ["cat", "--", "x.txt"],
      workspaceRoot: "/tmp/ws",
      readOnly: true,
      env: { BUTLER_V5_SANDBOX: "bubblewrap" },
      runner,
    })
    expect(result.ok).toBe(true)
    expect(runner.spawn).toHaveBeenCalled()
  })

  it("executeArgvInSandbox with stdinContent routes through executeWriteInSandbox (R16)", async () => {
    const spawnFn = vi.fn((_cmd: string, _args: readonly string[], _opts: unknown) => {
      // 模拟 bwrap + tee 写 stdin；返回 exit 0
      const stdinListeners: ((chunk: Buffer) => void)[] = []
      const handlers: Record<string, ((...a: unknown[]) => void)[]> = {
        close: [],
        error: [],
      }
      return {
        stdout: { on: (_e: string, _h: (b: Buffer) => void) => undefined },
        stderr: { on: (_e: string, _h: (b: Buffer) => void) => undefined },
        stdin: {
          write: (chunk: Buffer | string) => {
            stdinListeners.forEach((h) => h(typeof chunk === "string" ? Buffer.from(chunk) : chunk))
          },
          end: () => undefined,
        },
        pid: undefined,
        kill: () => undefined,
        on: (e: string, h: (...a: unknown[]) => void) => {
          if (!handlers[e]) handlers[e] = []
          handlers[e].push(h)
          // 同步 close 让 promise 解析
          if (e === "close") Promise.resolve().then(() => h(0))
          return undefined
        },
      } as unknown as ReturnType<typeof spawnFn>
    })
    const result = await executeWriteInSandbox({
      argv: ["tee", "x.txt"],
      workspaceRoot: "/tmp/ws",
      profileName: "workspace-write-network-deny",
      stdinContent: "hello bwrap\n",
      env: { BUTLER_V5_SANDBOX: "bubblewrap" },
      spawnFn: spawnFn as unknown as typeof ChildProcessSpawn,
    })
    expect(result.ok).toBe(true)
    expect(spawnFn).toHaveBeenCalledTimes(1)
    // 验 program 是 bwrap + argv 是 buildBubblewrapArgs 输出（以 --die-with-parent 起）
    const call = spawnFn.mock.calls[0] ?? []
    const args = call[1] as readonly string[]
    expect(args[0]).toBe("--die-with-parent")
  })

  it("executeWriteInSandbox fail-closed on empty argv (R16)", async () => {
    const result = await executeWriteInSandbox({
      argv: [],
      workspaceRoot: "/tmp/ws",
      stdinContent: "x",
      env: { BUTLER_V5_SANDBOX: "bubblewrap" },
    })
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.reason).toMatch(/argv/)
  })

  it("executeWriteInSandbox rejects argv[0] with slash (R16)", async () => {
    const result = await executeWriteInSandbox({
      argv: ["/usr/bin/tee", "x.txt"],
      workspaceRoot: "/tmp/ws",
      stdinContent: "x",
      env: { BUTLER_V5_SANDBOX: "bubblewrap" },
    })
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.reason).toMatch(/shell-style/)
  })
})
