/**
 * R16 sandbox 扩面 architecture guard：
 * `apps/api/src/mcp-spawn.ts` 必须在 bare `child_process.spawn(command, ...)`
 * 之前出现 `isSandboxEnabled(...)` 检查（否则 bwrap gate 被 bypass）。
 *
 * 这是 R16.4 commit (`5cd5e660`) 的静态静态守护——任何对 mcp-spawn.ts
 * 的后续修改若意外去掉 bwrap 分支，本测试 fail，强制 operator 复审。
 */
import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { join } from "node:path"

describe("R16 architecture: MCP spawn must gate on isSandboxEnabled", () => {
  it("mcp-spawn.ts calls isSandboxEnabled before bare child_process.spawn(command, ...)", () => {
    const src = readFileSync(
      join(process.cwd(), "apps/api/src/mcp-spawn.ts"),
      "utf8",
    )
    // 静态检查：`isSandboxEnabled(hostEnv)` 调用必须先于裸 spawn 分支
    // （`spawn(command, ...)`，非 `spawn("bwrap", ...)`）
    const sandboxCallIdx = src.indexOf("isSandboxEnabled(")
    expect(sandboxCallIdx).toBeGreaterThan(-1)
    // 找 `spawn(` 出现的位置（跳过 string literal）
    const spawnCallMatches = [...src.matchAll(/\bspawn\(/g)]
    // 第一个 spawn 调用是 `spawn("bwrap", ...)`（bwrap 分支）；后续 spawn 调用
    // 在 `else` 块，是裸 `spawn(command, ...)` 分支
    const firstSpawn = spawnCallMatches[0]?.index ?? -1
    expect(firstSpawn).toBeGreaterThan(-1)
    expect(sandboxCallIdx).toBeLessThan(firstSpawn)
    // 至少有 2 个 spawn 调用：bwrap 分支 + 裸 spawn 分支
    expect(spawnCallMatches.length).toBeGreaterThanOrEqual(2)
    // 第一个 spawn 必须是 bwrap 分支
    const bwrapBranch = src.slice(firstSpawn, firstSpawn + 60)
    expect(bwrapBranch).toMatch(/spawn\(\s*"bwrap"/)
  })
})