import { describe, expect, it, vi } from "vitest"
import {
  buildBubblewrapArgs,
  DEFAULT_SANDBOX_PROFILE,
  preflightBubblewrap,
  runInBubblewrap,
  type ProcessRunner,
} from "./bubblewrap-runner.js"

describe("bubblewrap runner", () => {
  it("builds fail-closed argv with workspace bind and network deny", () => {
    const args = buildBubblewrapArgs(DEFAULT_SANDBOX_PROFILE, ["echo", "hi"])
    expect(args).toContain("--unshare-net")
    expect(args).toContain("--bind")
    expect(args.at(-2)).toBe("echo")
    expect(args.at(-1)).toBe("hi")
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
