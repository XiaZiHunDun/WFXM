// Anchors: workspace tools dispatch through the sandbox runner, and subprocess
// runners never import Core (no second Run Engine). Merged from R16 and the
// former §16 process-boundary guard.
import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { join } from "node:path"

const WORKSPACE_TOOLS = join(process.cwd(), "apps/api/src/workspace-tools.ts")

const SUBPROCESS_RUNNERS = [
  join(process.cwd(), "packages/adapters/src/sandbox/bubblewrap-runner.ts"),
  join(process.cwd(), "packages/adapters/src/sandbox/slirp-egress.ts"),
  join(process.cwd(), "apps/api/src/mcp-spawn.ts"),
]

const CORE_IMPORT_PATTERNS = [
  /from\s+["']@butler\/runtime\/(?:execution|agent-kernel|run-engine|decision|policy-gate|capability-boundary|scoped-grant-service)/,
  /from\s+["']@butler\/adapters\/llm/,
  /from\s+["']@butler\/domain\/runtime\/(?:delegate-runtime|run-trigger)/,
]

describe("workspace sandbox architecture", () => {
  it("read_file / write_file dispatch through the bubblewrap sandbox runner", () => {
    const src = readFileSync(WORKSPACE_TOOLS, "utf8")
    expect(src).toMatch(/@butler\/adapters\/sandbox\/bubblewrap-runner\.js/)
    const readStart = src.indexOf("makeReadFileTool")
    const writeStart = src.indexOf("makeWriteFileTool")
    expect(readStart).toBeGreaterThan(-1)
    expect(writeStart).toBeGreaterThan(-1)
    const readBlock = src.slice(readStart, writeStart)
    expect(readBlock).toMatch(/executeArgvInSandbox/)
    const writeBlock = src.slice(writeStart)
    expect(writeBlock).toMatch(/stdinContent/)
  })

  it("subprocess runners never import Core (no second Run Engine)", () => {
    const violations: string[] = []
    for (const file of SUBPROCESS_RUNNERS) {
      const src = readFileSync(file, "utf8")
      for (const re of CORE_IMPORT_PATTERNS) {
        if (re.test(src)) violations.push(`${file}: ${re.source}`)
      }
    }
    expect(violations).toEqual([])
  })
})
