import { describe, expect, it } from "vitest"
import { buildChildSystemPrompt } from "./subagent-worker.js"

describe("buildChildSystemPrompt", () => {
  it("enforces tool-first execution and verification before completion", () => {
    const prompt = buildChildSystemPrompt("developer", [
      { name: "write_file" },
      { name: "list_files" },
    ])
    expect(prompt).toContain("write_file")
    expect(prompt).toContain("list_files")
    expect(prompt).toContain("原生 tool call")
    expect(prompt).toContain("核对")
    // Phase 7 fix F12: avoid stuck-loop aborts on repeated inspection commands.
    expect(prompt).toContain("不要用 run_command 反复")
    expect(prompt).toContain("不要原样重跑第三次")
    // Phase 7 fix F23: verification tasks must run the gate first; stale .next
    // makes later builds hang, so the child needs a cleanup hint.
    expect(prompt).toContain("先直接跑 pnpm typecheck 与 pnpm build")
    expect(prompt).toContain("rmSync('.next'")
    // F26: self-tests must not leave rows behind in the app's real database.
    expect(prompt).toContain("不要污染仓库数据")
    expect(prompt).toContain("残留 id")
  })

  it("tells a tool-less child to answer in prose only", () => {
    const prompt = buildChildSystemPrompt("general", [])
    expect(prompt).toContain("没有可用工具")
  })
})
