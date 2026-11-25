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
  })

  it("tells a tool-less child to answer in prose only", () => {
    const prompt = buildChildSystemPrompt("general", [])
    expect(prompt).toContain("没有可用工具")
  })
})
