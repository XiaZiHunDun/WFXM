import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import {
  buildWechatInboundMessages,
  generateLLMReply,
  stubReply,
  type LLMReplyLogger,
} from "./wechat-inbound-llm.js"

const ORIGINAL_ENV = { ...process.env }

describe("wechat-inbound-llm", () => {
  beforeEach(() => {
    for (const k of Object.keys(process.env)) delete process.env[k]
    Object.assign(process.env, ORIGINAL_ENV)
  })

  afterEach(() => {
    for (const k of Object.keys(process.env)) delete process.env[k]
    Object.assign(process.env, ORIGINAL_ENV)
    vi.restoreAllMocks()
  })

  it("buildWechatInboundMessages returns system + user tuple", () => {
    const msgs = buildWechatInboundMessages("hello")
    expect(msgs).toHaveLength(2)
    expect(msgs[0]?.role).toBe("system")
    expect(msgs[1]?.role).toBe("user")
    expect(msgs[1]?.content).toBe("hello")
  })

  // D60 T2.1 (audit #3 F-02): owner-facing reply must omit raw fromUserId +
// raw projectId + 'MVP stub reply' jargon (3x D48 §4 violation).
it("stubReply omits fromUserId, projectId, and MVP jargon", () => {
  const reply = stubReply("hi", "u-1", "proj-1")
  expect(reply).not.toContain("u-1")
  expect(reply).not.toContain("proj-1")
  expect(reply).not.toMatch(/MVP stub/)
  expect(reply).not.toMatch(/v5 received/)
  // Owner still gets confirmation the message was received.
  expect(reply).toContain("已收到")
})

  it("generateLLMReply returns stub when no LLM key is configured", async () => {
    const reply = await generateLLMReply({
      content: "hi",
      fromUserId: "u-1",
      projectId: "wechat",
      env: {},
    })
    // D60 T2.1 (audit #3 F-02): owner-facing fallback no longer surfaces
// raw fromUserId / raw projectId / 'MVP stub reply' jargon.
expect(reply).not.toMatch(/MVP stub/)
    expect(reply).not.toMatch(/u-1/)
    expect(reply).not.toMatch(/project=/)
    expect(reply).toContain("已收到")
  })

  it("generateLLMReply falls back to stub when LLM call fails (sanitized env)", async () => {
    // No real API key; the adapter call will fail. The fallback
    // contract is what we assert.
    const silent: LLMReplyLogger = { error: () => undefined }
    const reply = await generateLLMReply({
      content: "hi",
      fromUserId: "u-1",
      projectId: "wechat",
      env: { ANTHROPIC_API_KEY: "fail-key" },
      logger: silent,
    })
    // D60 T2.1: same — owner-facing fallback doesn't echo internal jargon.
    expect(reply).not.toMatch(/MVP stub/)
    expect(reply).not.toMatch(/u-1/)
    expect(reply).toContain("已收到")
  })

  it("generateLLMReply logs to the provided logger when LLM call fails", async () => {
    const errorSpy = vi.fn()
    const spyLogger: LLMReplyLogger = { error: errorSpy }
    await generateLLMReply({
      content: "hi",
      fromUserId: "u-2",
      projectId: "wechat",
      env: { DEEPSEEK_API_KEY: "fail-key" },
      logger: spyLogger,
    })
    expect(errorSpy).toHaveBeenCalledTimes(1)
    expect(errorSpy.mock.calls[0]?.[0]).toContain("u-2")
  })

  it("system prompt prefers read_file over run_command for file discovery", () => {
    const msgs = buildWechatInboundMessages("hi", {}, { fromUserId: "u-1" })
    const sys = msgs[0]?.content ?? ""
    expect(sys).toMatch(/prefer read_file|read_file.*(优先|first|before).*run_command/i)
    expect(sys).toMatch(/run_command/i)
  })

  it("system prompt instructs convergence after file discovery", () => {
    const msgs = buildWechatInboundMessages("hi", {}, { fromUserId: "u-1" })
    const sys = msgs[0]?.content ?? ""
    expect(sys).toMatch(/convergence|commit.*plan|forward motion|1-2 file-discovery/i)
  })
})
