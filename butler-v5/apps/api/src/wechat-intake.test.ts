import { describe, expect, it } from "vitest"
import {
  classifyWechatIntent,
  resolveIntakeLoopOptions,
} from "./wechat-intake.js"
import { resolveToolNamesForMode } from "./wechat-tool-profile.js"

describe("wechat-intake", () => {
  it("classifies dev session and dev task", () => {
    expect(classifyWechatIntent("开发模式").kind).toBe("dev_session")
    expect(classifyWechatIntent("帮我实现一个 hello 工具").kind).toBe("dev_task")
    expect(classifyWechatIntent("你好").kind).toBe("chat")
    expect(classifyWechatIntent("切到 WFXM").kind).toBe("switch_project")
  })

  it("keeps ping/pwd/几点 as chat", () => {
    expect(classifyWechatIntent("ping").kind).toBe("chat")
    expect(classifyWechatIntent("pwd").kind).toBe("chat")
    expect(classifyWechatIntent("现在几点").kind).toBe("chat")
    expect(classifyWechatIntent("运行 pwd 命令").kind).toBe("chat")
  })

  it("classifies fuzzy dev short sentences as dev_task", () => {
    expect(classifyWechatIntent("能不能加个缓存").kind).toBe("dev_task")
    expect(classifyWechatIntent("把这个 bug 修一下").kind).toBe("dev_task")
    expect(classifyWechatIntent("写个 hello world 工具").kind).toBe("dev_task")
  })

  it("classifies write_file / run_command literals as dev_task", () => {
    expect(classifyWechatIntent("write_file 写入 a.txt 内容 hi").kind).toBe("dev_task")
    expect(classifyWechatIntent("run_command argv=[\"pwd\"]").kind).toBe("dev_task")
  })

  it("plan mode hides exec tools", () => {
    const plan = resolveToolNamesForMode({ includeExecTools: false })
    expect(plan).not.toContain("run_command")
    expect(plan).not.toContain("write_file")
    expect(plan).toContain("read_file")

    const legacyDirect = resolveToolNamesForMode({
      includeExecTools: true,
      env: { BUTLER_V5_SUBAGENT_ENABLED: "1", BUTLER_V5_DEV_DIRECT_EXEC: "1" },
    })
    expect(legacyDirect).toContain("run_command")
    expect(legacyDirect).toContain("write_file")
    expect(legacyDirect).not.toContain("delegate_to_subagent")
  })

  it("dev_task intake uses scheme B plan+delegate (no main-loop exec)", () => {
    const env = {
      ...process.env,
      BUTLER_V5_WECHAT_TOOL_ALLOWLIST_PATH: "",
      BUTLER_V5_SUBAGENT_ENABLED: "1",
      BUTLER_V5_DEV_DIRECT_EXEC: "0",
    }
    const opts = resolveIntakeLoopOptions({
      intent: { kind: "dev_task", goal: "fix bug" },
      projectId: "wechat",
      env,
    })
    expect(opts.includeExecTools).toBe(false)
    expect(opts.requiresDevSession).toBe(true)
    expect(opts.allowedToolNames).toContain("delegate_to_subagent")
    expect(opts.allowedToolNames).not.toContain("write_file")
  })

  it("chat intake keeps plan-only tools", () => {
    const env = { ...process.env, BUTLER_V5_WECHAT_TOOL_ALLOWLIST_PATH: "" }
    const opts = resolveIntakeLoopOptions({
      intent: { kind: "chat" },
      projectId: "wechat",
      env,
    })
    expect(opts.includeExecTools).toBe(false)
    expect(opts.allowedToolNames).not.toContain("run_command")
  })
})
