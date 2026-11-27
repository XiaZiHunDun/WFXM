import { mkdtempSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import {
  buildDevVerifyFixTask,
  formatDevQualityReply,
  isDevVerifyAutofixEnabled,
  isDevVerifyInlineEnabled,
  resolveDevVerifyArgv,
  resolveDevVerifyCwd,
  scheduleAsyncDevVerify,
  shouldAutoDevVerify,
  shouldAutoDevVerifySubagent,
  shouldAutofixDevFailure,
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
      BUTLER_V5_WORKSPACE_ROOT: process.cwd(),
      BUTLER_V5_QUALITY_GATE_CONFIG: `${process.cwd()}/config/quality-gate.json`,
    })
    expect(cwd).toBe(process.cwd())
  })

  it("resolveDevVerifyCwd falls back to the workspace root for unknown projects", () => {
    const cwd = resolveDevVerifyCwd("no-such-project", {
      BUTLER_V5_WORKSPACE_ROOT: process.cwd(),
      BUTLER_V5_QUALITY_GATE_CONFIG: `${process.cwd()}/config/quality-gate.json`,
    })
    expect(cwd).toBe(process.cwd())
  })

  it("resolveDevVerifyCwd falls back to the root when the configured cwd is missing", () => {
    const dir = mkdtempSync(join(tmpdir(), "dev-verify-"))
    const cfgPath = join(dir, "qg.json")
    writeFileSync(
      cfgPath,
      JSON.stringify({ version: 1, projects: { ghost: { cwd: "does-not-exist" } } }),
    )
    const cwd = resolveDevVerifyCwd("ghost", {
      BUTLER_V5_WORKSPACE_ROOT: process.cwd(),
      BUTLER_V5_QUALITY_GATE_CONFIG: cfgPath,
    })
    expect(cwd).toBe(process.cwd())
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
        isDevVerifyInlineEnabled(falsy === undefined ? {} : { BUTLER_V5_DEV_VERIFY_INLINE: falsy }),
      ).toBe(false)
    }
  })

  // F32: a red gate must trigger (at most) one auto-fix round, not a
  // "done" reply with failing tests.
  it("isDevVerifyAutofixEnabled defaults on and can be turned off", () => {
    expect(isDevVerifyAutofixEnabled({})).toBe(true)
    for (const falsy of ["0", "false", "off"]) {
      expect(isDevVerifyAutofixEnabled({ BUTLER_V5_DEV_VERIFY_AUTOFIX: falsy })).toBe(false)
    }
  })

  it("buildDevVerifyFixTask carries the failing output and forbids redoing the feature", () => {
    const text = buildDevVerifyFixTask({
      task: "给工作台加查找替换",
      verify: {
        ok: false,
        exitCode: 1,
        commandLabel: "pnpm test",
        outputExcerpt: "not ok 25 - 断言失败",
        durationMs: 900,
      },
    })
    expect(text).toContain("给工作台加查找替换")
    expect(text).toContain("【验收未通过 · 自动续跑】")
    expect(text).toContain("pnpm test")
    expect(text).toContain("exit 1")
    expect(text).toContain("not ok 25")
    expect(text).toContain("不要重做已完成的功能")
  })

  it("buildDevVerifyFixTask tolerates an empty gate output", () => {
    const text = buildDevVerifyFixTask({
      task: "修复文案",
      verify: {
        ok: false,
        exitCode: 2,
        commandLabel: "pnpm typecheck",
        outputExcerpt: "   ",
        durationMs: 10,
      },
    })
    expect(text).toContain("(无输出)")
  })

  it("shouldAutofixDevFailure only fires for a red gate on a mutating child run", () => {
    const red = {
      ok: false,
      exitCode: 1,
      commandLabel: "pnpm test",
      outputExcerpt: "not ok",
      durationMs: 10,
    }
    const green = { ...red, ok: true, exitCode: 0 }
    expect(
      shouldAutofixDevFailure({ llmOk: true, verify: red, capabilities: ["developer", "write_file"] }),
    ).toBe(true)
    expect(
      shouldAutofixDevFailure({ llmOk: true, verify: green, capabilities: ["write_file"] }),
    ).toBe(false)
    expect(
      shouldAutofixDevFailure({ llmOk: false, verify: red, capabilities: ["write_file"] }),
    ).toBe(false)
    expect(
      shouldAutofixDevFailure({
        llmOk: true,
        waitingApproval: true,
        verify: red,
        capabilities: ["write_file"],
      }),
    ).toBe(false)
    expect(
      shouldAutofixDevFailure({ llmOk: true, verify: red, capabilities: ["general"] }),
    ).toBe(false)
    expect(
      shouldAutofixDevFailure({
        llmOk: true,
        verify: red,
        capabilities: ["write_file"],
        env: { BUTLER_V5_DEV_VERIFY_AUTOFIX: "0" },
      }),
    ).toBe(false)
    expect(
      shouldAutofixDevFailure({
        llmOk: true,
        verify: { ...red, ok: true },
        capabilities: ["run_command"],
      }),
    ).toBe(false)
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

  const fastEnv = {
    BUTLER_V5_WORKSPACE_ROOT: process.cwd(),
    BUTLER_V5_DEV_VERIFY_CMD: '["node","-e","0"]',
  }

  it("logs stderr and resolves when updateProjectState throws (audit F-10)", async () => {
    updateProjectStateMock.mockImplementationOnce(() => {
      throw new Error("DB connection lost")
    })
    // Fast verify command so the test never shells out to the real suite.
    const cwd = resolveDevVerifyCwd("wechat", fastEnv)
    await expect(
      scheduleAsyncDevVerify({
        projectId: "wechat",
        fromUserId: "owner",
        baseReply: "已写",
        cwd,
        env: fastEnv,
      }),
    ).resolves.toBeUndefined()
    expect(stderrSpy).toHaveBeenCalledWith(
      "[dev-quality-gate] background verify crashed:",
      "DB connection lost",
    )
  })

  it("does not log when updateProjectState succeeds", async () => {
    updateProjectStateMock.mockImplementationOnce(() => undefined)
    const cwd = resolveDevVerifyCwd("wechat", fastEnv)
    await scheduleAsyncDevVerify({
      projectId: "wechat",
      fromUserId: "owner",
      baseReply: "已写",
      cwd,
      env: fastEnv,
    })
    expect(stderrSpy).not.toHaveBeenCalled()
  })
})
