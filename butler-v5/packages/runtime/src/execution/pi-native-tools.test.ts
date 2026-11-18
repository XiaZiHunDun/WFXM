import { mkdtempSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import type { AgentTool } from "@butler/pi-agent"
import { createPiNativeTools, resolveInsideWorkspace } from "./pi-native-tools.js"

let root: string

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "pi-tools-"))
})

afterEach(() => {
  rmSync(root, { recursive: true, force: true })
})

function toolOf(tools: readonly AgentTool[], name: string): AgentTool {
  const tool = tools.find((entry) => entry.name === name)
  if (!tool) throw new Error(`missing tool ${name}`)
  return tool
}

async function run(tools: readonly AgentTool[], name: string, args: Record<string, unknown>) {
  return toolOf(tools, name).execute(`call-${name}`, args)
}

describe("pi native tools", () => {
  it("writes, reads and edits a file", async () => {
    const tools = createPiNativeTools({ cwd: root })
    const written = await run(tools, "write", { path: "src/a.ts", content: "export const a = 1\n" })
    expect(written.isError).toBeFalsy()

    const read = await run(tools, "read", { path: "src/a.ts" })
    expect(read.content[0]).toMatchObject({ type: "text" })
    expect(JSON.stringify(read.content)).toContain("export const a = 1")

    const edited = await run(tools, "edit", {
      path: "src/a.ts",
      oldText: "a = 1",
      newText: "a = 2",
    })
    expect(edited.isError).toBeFalsy()
    const after = await run(tools, "read", { path: "src/a.ts" })
    expect(JSON.stringify(after.content)).toContain("a = 2")
  })

  it("rejects ambiguous edits unless replaceAll is set", async () => {
    const tools = createPiNativeTools({ cwd: root })
    await run(tools, "write", { path: "a.txt", content: "x x\n" })
    const ambiguous = await run(tools, "edit", { path: "a.txt", oldText: "x", newText: "y" })
    expect(ambiguous.isError).toBe(true)

    const all = await run(tools, "edit", {
      path: "a.txt",
      oldText: "x",
      newText: "y",
      replaceAll: true,
    })
    expect(all.isError).toBeFalsy()
    const read = await run(tools, "read", { path: "a.txt" })
    expect(JSON.stringify(read.content)).toContain("y y")
  })

  it("runs bash inside the workspace and reports non-zero exits", async () => {
    const tools = createPiNativeTools({ cwd: root })
    const ok = await run(tools, "bash", { command: "echo hello" })
    expect(ok.isError).toBeFalsy()
    expect(JSON.stringify(ok.content)).toContain("hello")

    const failed = await run(tools, "bash", { command: "exit 3" })
    expect(failed.isError).toBe(true)
    expect(JSON.stringify(failed.content)).toContain("exit 3")
  })

  it("greps, finds and lists", async () => {
    const tools = createPiNativeTools({ cwd: root })
    writeFileSync(join(root, "a.ts"), "const needle = 1\n")
    writeFileSync(join(root, "b.md"), "needle docs\n")

    const grep = await run(tools, "grep", { pattern: "needle" })
    expect(JSON.stringify(grep.content)).toContain("a.ts:1")

    const find = await run(tools, "find", { pattern: "*.ts" })
    expect(JSON.stringify(find.content)).toContain("a.ts")
    expect(JSON.stringify(find.content)).not.toContain("b.md")

    const ls = await run(tools, "ls", {})
    expect(JSON.stringify(ls.content)).toContain("a.ts")
  })

  it("rejects path escapes", async () => {
    const tools = createPiNativeTools({ cwd: root })
    const parent = await run(tools, "read", { path: "../outside.txt" })
    expect(parent.isError).toBe(true)

    const absolute = await run(tools, "write", { path: "/etc/passwd", content: "x" })
    expect(absolute.isError).toBe(true)

    const direct = await resolveInsideWorkspace(root, "../outside.txt")
    expect(direct.ok).toBe(false)
  })
})
