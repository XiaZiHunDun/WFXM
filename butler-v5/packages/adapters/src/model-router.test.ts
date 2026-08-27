import { describe, expect, it } from "vitest"
import { pickExecLLM, pickLLMForRole, pickPlanLLM, execModelTrace } from "./model-router.js"

const emptyEnv: NodeJS.ProcessEnv = {}

describe("model-router", () => {
  it("pickPlanLLM prefers DeepSeek when configured", () => {
    const adapter = pickPlanLLM({
      DEEPSEEK_API_KEY: "sk-ds",
      DEEPSEEK_MODEL: "deepseek-chat",
      ...emptyEnv,
    })
    expect(adapter).toBeDefined()
    expect(typeof adapter?.complete).toBe("function")
  })

  it("pickExecLLM prefers MiniMax when configured", () => {
    const adapter = pickExecLLM({
      MINIMAX_API_KEY: "sk-mm",
      BUTLER_V5_MODEL_EXEC: "MiniMax-M3",
      ...emptyEnv,
    })
    expect(adapter).toBeDefined()
  })

  it("MiniMax MINIMAX_BASE_URL with /v1 does not double-path in openai-compatible", async () => {
    let requestedUrl = ""
    const fetchMock: typeof fetch = async (input) => {
      requestedUrl = String(input)
      return new Response(
        JSON.stringify({
          choices: [{ message: { role: "assistant", content: "ok" }, finish_reason: "stop" }],
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      )
    }
    const { makeOpenAICompatibleAdapter } = await import("./llm/openai-compatible.js")
    const adapter = makeOpenAICompatibleAdapter({
      apiKey: "sk-mm",
      baseUrl: "https://api.minimax.io",
      model: "MiniMax-M3",
      fetch: fetchMock,
    })
    const { Effect } = await import("effect")
    await Effect.runPromise(adapter.complete([{ role: "user", content: "hi" }]))
    expect(requestedUrl).toBe("https://api.minimax.io/v1/chat/completions")
  })

  it("pickExecLLM falls back to plan when MiniMax missing", () => {
    const adapter = pickExecLLM({
      DEEPSEEK_API_KEY: "sk-ds",
      ...emptyEnv,
    })
    expect(adapter).toBeDefined()
  })

  it("execModelTrace reports MiniMax or plan fallback", () => {
    expect(
      execModelTrace({
        MINIMAX_API_KEY: "sk-mm",
        BUTLER_V5_MODEL_EXEC: "MiniMax-M3",
        ...emptyEnv,
      }),
    ).toBe("exec:MiniMax-M3")
    expect(
      execModelTrace({
        DEEPSEEK_API_KEY: "sk-ds",
        ...emptyEnv,
      }),
    ).toBe("exec-fallback:plan")
  })

  it("pickLLMForRole routes by role", () => {
    const env = {
      DEEPSEEK_API_KEY: "sk-ds",
      MINIMAX_API_KEY: "sk-mm",
      ...emptyEnv,
    }
    expect(pickLLMForRole(env, "plan")).toBeDefined()
    expect(pickLLMForRole(env, "exec")).toBeDefined()
    expect(pickLLMForRole(env, "intake")).toBeDefined()
  })
})
