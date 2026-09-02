import { describe, expect, it } from "vitest"
import {
  classifyWechatIntentWithLlm,
  isWechatIntakeLlmEnabled,
  shouldSkipIntakeLlm,
} from "./wechat-intake-llm.js"
import { classifyWechatIntent } from "./wechat-intake.js"

describe("wechat-intake-llm", () => {
  it("is disabled by default", () => {
    expect(isWechatIntakeLlmEnabled({})).toBe(false)
  })

  it("honours the shared 1/true/yes/on env convention", () => {
    for (const truthy of ["1", "true", "yes", "on"]) {
      expect(isWechatIntakeLlmEnabled({ BUTLER_V5_INTAKE_LLM: truthy })).toBe(true)
    }
    for (const falsy of ["0", "false", "off", ""]) {
      expect(isWechatIntakeLlmEnabled({ BUTLER_V5_INTAKE_LLM: falsy })).toBe(false)
    }
  })

  it("falls back to rules when LLM disabled", async () => {
    const fallback = classifyWechatIntent("你好")
    const out = await classifyWechatIntentWithLlm({
      content: "你好",
      fallback,
      env: { BUTLER_V5_INTAKE_LLM: "0" },
    })
    expect(out.source).toBe("rules")
    expect(out.intent.kind).toBe("chat")
  })

  it("falls back when LLM enabled but no API key", async () => {
    const fallback = classifyWechatIntent("ping")
    const out = await classifyWechatIntentWithLlm({
      content: "ping",
      fallback,
      env: {
        BUTLER_V5_INTAKE_LLM: "1",
        DEEPSEEK_API_KEY: "",
        ANTHROPIC_API_KEY: "",
      },
    })
    expect(out.source).toBe("rules")
    expect(out.intent.kind).toBe("chat")
  })

  it("skips LLM when rules already locked dev_task (write_file literal)", async () => {
    const content = "write_file 写入 butler-v5/tmp.txt 内容 ok"
    const fallback = classifyWechatIntent(content)
    expect(fallback.kind).toBe("dev_task")
    expect(shouldSkipIntakeLlm(fallback)).toBe(true)
    const out = await classifyWechatIntentWithLlm({
      content,
      fallback,
      env: { BUTLER_V5_INTAKE_LLM: "1", DEEPSEEK_API_KEY: "sk-fake" },
    })
    expect(out.source).toBe("rules")
    expect(out.intent.kind).toBe("dev_task")
  })
})
