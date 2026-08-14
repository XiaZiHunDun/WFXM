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

  it("stubReply includes fromUserId and projectId", () => {
    const reply = stubReply("hi", "u-1", "proj-1")
    expect(reply).toContain("u-1")
    expect(reply).toContain("proj-1")
    expect(reply).toContain("MVP stub reply")
  })

  it("generateLLMReply returns stub when no LLM key is configured", async () => {
    const reply = await generateLLMReply({
      content: "hi",
      fromUserId: "u-1",
      projectId: "wechat",
      env: {},
    })
    expect(reply).toContain("MVP stub reply")
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
    expect(reply).toContain("MVP stub reply")
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
})
