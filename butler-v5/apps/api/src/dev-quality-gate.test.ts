import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import {
  formatDevQualityReply,
  isDevVerifyInlineEnabled,
  resolveDevVerifyArgv,
  resolveDevVerifyCwd,
  scheduleAsyncDevVerify,
  shouldAutoDevVerify,
  shouldAutoDevVerifySubagent,
} from "./dev-quality-gate.js"

// D57 audit #3 F-10: lock the contract that scheduleAsyncDevVerify logs
// to stderr (instead of swallowing silently) when the background pipeline
// throws — otherwise project state can stay stuck on '验收运行中' with no
// operator signal.
const updateProjectStateMock = vi.fn()

vi.mock("./project-state.js", () => ({
  updateProjectState: (...args: unknown[]) => updateProjectStateMock(...args),
}))

describe("dev-quality-gate", () => {
  it("resolveDevVerifyArgv defaults to pnpm test", () => {
    expect(resolveDevVerifyArgv({})).toEqual(["pnpm", "test"])
  })

  it("resolveDevVerifyArgv parses JSON array", () => {
    expect(
      resolveDevVerifyArgv({
        BUTLER_V5_DEV_VERIFY_CMD: '["echo","ok"]',
      }),
    ).toEqual(["echo", "ok"])
  })

  it("resolveDevVerifyCwd uses quality gate project cwd", () => {
    const cwd = resolveDevVerifyCwd("wechat", {
      BUTLER_V5_WORKSPACE_ROOT: "/repo",
      BUTLER_V5_QUALITY_GATE_CONFIG: `${process.cwd()}/config/quality-gate.json`,
    })
    expect(cwd.endsWith("butler-v5")).toBe(true)
  })

  it("shouldAutoDevVerify requires direct exec tools in traces", () => {
    const env = { BUTLER_V5_DEV_VERIFY_ENABLED: "1" }
    expect(
      shouldAutoDevVerify({
        includeExecTools: true,
        loop: { finalDecision: "Respond", toolCalls: 0, traces: [] },
        env,
      }),
    ).toBe(false)
    expect(
      shouldAutoDevVerify({
        includeExecTools: true,
        loop: {
          finalDecision: "Respond",
          toolCalls: 1,
          traces: ["delegate_to_subagent@0: ok"],
        },
        env,
      }),
    ).toBe(false)
    expect(
      shouldAutoDevVerify({
        includeExecTools: true,
        loop: {
          finalDecision: "Respond",
          toolCalls: 2,
          traces: ["write_file@0: ok"],
        },
        env,
      }),
    ).toBe(true)
    expect(
      shouldAutoDevVerify({
        includeExecTools: true,
        loop: { finalDecision: "WaitForApproval", toolCalls: 1, traces: ["run_command@0: x"] },
        env,
      }),
    ).toBe(false)
  })

  it("shouldAutoDevVerifySubagent detects exec capabilities", () => {
    expect(
      shouldAutoDevVerifySubagent({
        capabilities: ["write_file"],
        ok: true,
        env: { BUTLER_V5_DEV_VERIFY_ENABLED: "1" },
      }),
    ).toBe(true)
    expect(
      shouldAutoDevVerifySubagent({
        capabilities: ["general"],
        ok: true,
        env: { BUTLER_V5_DEV_VERIFY_ENABLED: "1" },
      }),
    ).toBe(false)
  })

  it("formatDevQualityReply structures WeChat output", () => {
    const text = formatDevQualityReply({
      projectId: "wechat",
      ownerLabel: "WFXM",
      baseReply: "已完成修改",
      verify: {
        ok: true,
        exitCode: 0,
        commandLabel: "pnpm test",
        outputExcerpt: "all green",
        durationMs: 1200,
      },
      touchedPaths: ["apps/api/src/foo.ts"],
    })
    expect(text).toContain("【开发验收】项目 WFXM")
    expect(text).not.toContain("项目 wechat")
    expect(text).toContain("foo.ts")
    expect(text).toContain("✓")
    expect(text).toContain("已完成修改")
  })

  it("isDevVerifyInlineEnabled honours the shared 1/true/yes/on env convention", () => {
    for (const truthy of ["1", "true", "yes", "on"]) {
      expect(isDevVerifyInlineEnabled({ BUTLER_V5_DEV_VERIFY_INLINE: truthy })).toBe(true)
    }
    for (const falsy of ["0", "false", "off", "", undefined]) {
      expect(
        isDevVerifyInlineEnabled(
          falsy === undefined ? {} : { BUTLER_V5_DEV_VERIFY_INLINE: falsy },
        ),
      ).toBe(false)
    }
  })
})

describe("scheduleAsyncDevVerify", () => {
  let stderrSpy: ReturnType<typeof vi.spyOn>
  let savedEnv: NodeJS.ProcessEnv

  beforeEach(() => {
    savedEnv = { ...process.env }
    stderrSpy = vi.spyOn(console, "error").mockImplementation(() => undefined)
    updateProjectStateMock.mockReset()
  })

  afterEach(() => {
    process.env = savedEnv
    stderrSpy.mockRestore()
  })

  it("logs stderr and resolves when updateProjectState throws (audit F-10)", async () => {
    updateProjectStateMock.mockImplementationOnce(() => {
      throw new Error("DB connection lost")
    })
    // cwd points to butler-v5 (a real git repo) so the pre-verify git
    // commands succeed; the throw is injected via updateProjectStateMock.
    const cwd = resolveDevVerifyCwd("wechat", {})
    await expect(
      scheduleAsyncDevVerify({
        projectId: "wechat",
        fromUserId: "owner",
        baseReply: "已写",
        cwd,
        env: {},
      }),
    ).resolves.toBeUndefined()
    expect(stderrSpy).toHaveBeenCalledWith(
      "[dev-quality-gate] background verify crashed:",
      "DB connection lost",
    )
  })

  it("does not log when updateProjectState succeeds", async () => {
    updateProjectStateMock.mockImplementationOnce(() => undefined)
    const cwd = resolveDevVerifyCwd("wechat", {})
    await scheduleAsyncDevVerify({
      projectId: "wechat",
      fromUserId: "owner",
      baseReply: "已写",
      cwd,
      env: {},
    })
    expect(stderrSpy).not.toHaveBeenCalled()
  })
})
