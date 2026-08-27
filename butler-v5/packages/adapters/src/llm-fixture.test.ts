import { describe, expect, it } from "vitest"
import { Effect } from "effect"
import { join } from "node:path"
import {
  makeFixtureLLMAdapter,
  resetFixtureLLMCounters,
  fixtureLLMPath,
} from "./llm-fixture.js"

describe("llm-fixture", () => {
  const fixtureDir = join(process.cwd(), "config/llm-fixtures/wechat")

  it("reads plan fixture responses in order", async () => {
    resetFixtureLLMCounters()
    const adapter = makeFixtureLLMAdapter({ fixtureDir, role: "plan" })
    const first = await Effect.runPromise(adapter.complete([]))
    expect(first.content).toContain("Respond")
    const second = await Effect.runPromise(adapter.complete([]))
    expect(second.content).toContain("Delegate")
  })

  it("fixtureLLMPath resolves role file", () => {
    expect(fixtureLLMPath(fixtureDir, "exec")).toContain("exec.json")
  })
})
