import { describe, it, expect } from "vitest"
import { Effect } from "effect"
import { runWorkflow, MockWorkflowServiceLive } from "./index.js"

describe("application/run-workflow", () => {
  it("returns workflow id after parallel execution", async () => {
    const program = Effect.provide(
      runWorkflow({
        mainFile: "src/App.tsx",
        expectedLinks: ["src/App.test.tsx", "src/index.ts", "src/utils.ts"],
      }),
      MockWorkflowServiceLive,
    )

    const result = await Effect.runPromise(program)
    expect(result).toMatch(/^wf-\d+$/)
  })

  it("handles empty expectedLinks", async () => {
    const program = Effect.provide(
      runWorkflow({
        mainFile: "src/readme.md",
        expectedLinks: [],
      }),
      MockWorkflowServiceLive,
    )

    const result = await Effect.runPromise(program)
    expect(result).toMatch(/^wf-\d+$/)
  })
})
