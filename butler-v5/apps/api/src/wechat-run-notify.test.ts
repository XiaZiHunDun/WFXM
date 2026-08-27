import { describe, expect, it } from "vitest"
import {
  formatSubagentCompletionNotify,
  isRunNotifyEnabled,
  sendWechatProactiveNotify,
} from "./wechat-run-notify.js"

describe("wechat-run-notify", () => {
  it("formats subagent completion message", () => {
    const text = formatSubagentCompletionNotify({
      role: "general",
      task: "summarize README",
      reply: "Done.",
      ok: true,
    })
    expect(text).toContain("【子代理完成】")
    expect(text).toContain("summarize README")
  })

  it("isRunNotifyEnabled respects env", () => {
    expect(isRunNotifyEnabled({})).toBe(false)
    expect(isRunNotifyEnabled({ BUTLER_V5_RUN_NOTIFY_ENABLED: "1" })).toBe(true)
  })

  it("sendWechatProactiveNotify writes mock outbox when configured", async () => {
    const path = `/tmp/butler-notify-test-${Date.now()}.jsonl`
    const result = await sendWechatProactiveNotify({
      to: "u-mock",
      text: "hello",
      env: {
        BUTLER_V5_RUN_NOTIFY_ENABLED: "1",
        BUTLER_V5_RUN_NOTIFY_MOCK_OUTBOX: path,
      },
    })
    expect(result.ok).toBe(true)
    const { readFileSync, rmSync } = await import("node:fs")
    const line = readFileSync(path, "utf8").trim()
    expect(line).toContain("u-mock")
    rmSync(path, { force: true })
  })

  it("sendWechatProactiveNotify skips when disabled", async () => {
    const result = await sendWechatProactiveNotify({
      to: "u1",
      text: "hello",
      env: {},
    })
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.reason).toContain("disabled")
  })
})
