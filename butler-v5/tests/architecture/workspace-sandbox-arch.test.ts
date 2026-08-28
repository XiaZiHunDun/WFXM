/**
 * R16 sandbox 扩面 architecture guard：
 * `apps/api/src/workspace-tools.ts` 的 `makeReadFileTool` + `makeWriteFileTool`
 * 必须 import `@butler/adapters/sandbox/bubblewrap-runner.js`（即 dispatch 到
 * bwrap）。
 *
 * 注意：本守卫锁住的是 R16.3 commit（operator manual override 应用
 * `workspace-tools.ts` 编辑后落 main）。commit 落前本测试 fail，operator
 * apply 完 commit 后本测试自动 pass。
 */
import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { join } from "node:path"

describe("R16 architecture: workspace read_file / write_file dispatch through bwrap", () => {
  it("workspace-tools.ts imports bubblewrap-runner.js inside read_file path", () => {
    const src = readFileSync(
      join(process.cwd(), "apps/api/src/workspace-tools.ts"),
      "utf8",
    )
    expect(src).toMatch(/@butler\/adapters\/sandbox\/bubblewrap-runner\.js/)
  })

  it("workspace-tools.ts makeReadFileTool invokes executeArgvInSandbox", () => {
    const src = readFileSync(
      join(process.cwd(), "apps/api/src/workspace-tools.ts"),
      "utf8",
    )
    // 简化：在 makeReadFileTool 块范围内需引用 executeArgvInSandbox
    const readFileIdx = src.indexOf("makeReadFileTool")
    const writeFileIdx = src.indexOf("makeWriteFileTool")
    const nextExportIdx = src.indexOf("export function make", Math.max(readFileIdx, writeFileIdx))
    const lastIdx = nextExportIdx === -1 ? src.length : nextExportIdx
    const endIdx = Math.max(readFileIdx, writeFileIdx) > -1 ? lastIdx : src.length
    const range = readFileIdx > -1 ? src.slice(readFileIdx, endIdx) : src
    expect(range).toMatch(/executeArgvInSandbox/)
  })

  it("workspace-tools.ts makeWriteFileTool invokes executeArgvInSandbox with stdinContent", () => {
    const src = readFileSync(
      join(process.cwd(), "apps/api/src/workspace-tools.ts"),
      "utf8",
    )
    const writeFileIdx = src.indexOf("makeWriteFileTool")
    expect(writeFileIdx).toBeGreaterThan(-1)
    // 看 makeWriteFileTool 块范围内是否有 stdinContent 字段（write 走 tee-equivalent）
    const nextExportIdx = src.indexOf("export function make", writeFileIdx + 1)
    const endIdx = nextExportIdx === -1 ? src.length : nextExportIdx
    const range = src.slice(writeFileIdx, endIdx)
    expect(range).toMatch(/stdinContent/)
  })
})