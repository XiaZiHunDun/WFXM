import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
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

// D59 T5 (audit #3 F-07): each silent push-notify failure mode must leave
// a structured stderr line so operators can diagnose from logs alone.
// Without these logs the only signal is a boolean false return — owners
// (and operators) cannot tell WHY their push notification didn't arrive.
describe("wechat-run-notify observability (D59 T5 audit #3 F-07)", () => {
  let stderrSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    stderrSpy = vi.spyOn(console, "error").mockImplementation(() => {})
  })

  afterEach(() => {
    stderrSpy.mockRestore()
  })

  it("logs structured line when BUTLER_V5_RUN_NOTIFY_ENABLED=0", async () => {
    const result = await sendWechatProactiveNotify({
      to: "u1",
      text: "hello",
      env: {},
    })
    expect(result.ok).toBe(false)
    expect(stderrSpy).toHaveBeenCalledWith(
      expect.stringMatching(/\[wechat-run-notify\] skipped reason=run_notify_disabled/),
    )
  })

  it("logs structured line when recipient or message is empty", async () => {
    const result = await sendWechatProactiveNotify({
      to: "  ",
      text: "hello",
      env: { BUTLER_V5_RUN_NOTIFY_ENABLED: "1" },
    })
    expect(result.ok).toBe(false)
    expect(stderrSpy).toHaveBeenCalledWith(
      expect.stringMatching(/\[wechat-run-notify\] skipped reason=empty_recipient_or_message/),
    )
  })

  it("logs structured line when iLink not configured", async () => {
    const result = await sendWechatProactiveNotify({
      to: "u1",
      text: "hello",
      env: { BUTLER_V5_RUN_NOTIFY_ENABLED: "1" },
    })
    expect(result.ok).toBe(false)
    expect(stderrSpy).toHaveBeenCalledWith(
      expect.stringMatching(/\[wechat-run-notify\] skipped reason=ilink_not_configured/),
    )
  })
})
