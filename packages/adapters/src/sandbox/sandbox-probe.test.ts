import { describe, expect, it, vi } from "vitest"
import { probeSandboxNetworkIsolation } from "./sandbox-probe.js"
import type { ProcessRunner } from "./bubblewrap-runner.js"

describe("sandbox network probe", () => {
  it("reports disabled when bubblewrap env unset", async () => {
    const runner: ProcessRunner = {
      spawn: vi.fn(async () => ({ code: 0, stdout: "", stderr: "" })),
    }
    const result = await probeSandboxNetworkIsolation({
      workspaceRoot: "/tmp/ws",
      env: {},
      runner,
    })
    expect(result.sandboxEnabled).toBe(false)
    expect(result.ok).toBe(false)
  })

  it("passes when deny blocks and allow reaches probe", async () => {
    const runner: ProcessRunner = {
      spawn: vi.fn(async (_cmd, args) => {
        const hasUnshareNet = args.includes("--unshare-net")
        return hasUnshareNet
          ? { code: 1, stdout: "", stderr: "network blocked" }
          : { code: 0, stdout: "ok", stderr: "" }
      }),
    }
    const result = await probeSandboxNetworkIsolation({
      workspaceRoot: "/tmp/ws",
      env: { BUTLER_V5_SANDBOX: "bubblewrap" },
      runner,
      probeUrl: "http://127.0.0.1:9/probe",
    })
    expect(result.ok).toBe(true)
    expect(result.denyBlockedNetwork).toBe(true)
    expect(result.allowReachedNetwork).toBe(true)
  })

  it("fails when deny profile unexpectedly allows network", async () => {
    const runner: ProcessRunner = {
      spawn: vi.fn(async () => ({ code: 0, stdout: "leak", stderr: "" })),
    }
    const result = await probeSandboxNetworkIsolation({
      workspaceRoot: "/tmp/ws",
      env: { BUTLER_V5_SANDBOX: "bubblewrap" },
      runner,
    })
    expect(result.ok).toBe(false)
    expect(result.reason).toMatch(/deny profile did not block/i)
  })
})
