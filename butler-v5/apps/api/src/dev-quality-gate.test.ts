import { describe, expect, it } from "vitest"
import {
  formatDevQualityReply,
  resolveDevVerifyArgv,
  resolveDevVerifyCwd,
  shouldAutoDevVerify,
  shouldAutoDevVerifySubagent,
} from "./dev-quality-gate.js"

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
    expect(text).toContain("【开发验收】")
    expect(text).toContain("foo.ts")
    expect(text).toContain("✓")
    expect(text).toContain("已完成修改")
  })
})
