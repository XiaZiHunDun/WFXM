/**
 * R8.x.12 — sandbox path + argv helpers for read_file / run_command.
 */
import { mkdtempSync, mkdirSync, rmSync, symlinkSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, describe, expect, it } from "vitest"
import { runTool } from "@butler/runtime/tool-runtime.js"
import {
  ALLOWED_RUN_COMMANDS,
  makeReadFileTool,
  makeRunCommandTool,
  resolveUnderWorkspace,
} from "./workspace-tools.js"

describe("resolveUnderWorkspace", () => {
  let root: string

  afterEach(() => {
    if (root) rmSync(root, { recursive: true, force: true })
  })

  it("resolves a relative path inside the root", () => {
    root = mkdtempSync(join(tmpdir(), "ws-tools-"))
    writeFileSync(join(root, "note.txt"), "hi")
    const r = resolveUnderWorkspace(root, "note.txt")
    expect(r.ok).toBe(true)
    if (r.ok) expect(r.path).toBe(join(root, "note.txt"))
  })

  it("rejects path traversal", () => {
    root = mkdtempSync(join(tmpdir(), "ws-tools-"))
    const r = resolveUnderWorkspace(root, "../secret")
    expect(r.ok).toBe(false)
  })

  it("rejects an absolute path outside the root", () => {
    root = mkdtempSync(join(tmpdir(), "ws-tools-"))
    const r = resolveUnderWorkspace(root, "/etc/passwd")
    expect(r.ok).toBe(false)
  })
})

describe("makeReadFileTool", () => {
  let root: string

  afterEach(() => {
    if (root) rmSync(root, { recursive: true, force: true })
  })

  it("reads a utf-8 file under the workspace root", async () => {
    root = mkdtempSync(join(tmpdir(), "ws-tools-"))
    writeFileSync(join(root, "hello.txt"), "你好 butler")
    const tool = makeReadFileTool({ workspaceRoot: root })
    const result = await runTool(tool, { path: "hello.txt" }, { timeoutMs: 1000 })
    expect(result.ok).toBe(true)
    if (result.ok) expect(String(result.output)).toBe("你好 butler")
  })

  it("returns error envelope when path is missing", async () => {
    root = mkdtempSync(join(tmpdir(), "ws-tools-"))
    const tool = makeReadFileTool({ workspaceRoot: root })
    const result = await runTool(tool, {}, { timeoutMs: 1000 })
    expect(result.ok).toBe(false)
  })

  it("refuses a symlink that escapes the root", async () => {
    root = mkdtempSync(join(tmpdir(), "ws-tools-"))
    const outside = mkdtempSync(join(tmpdir(), "ws-outside-"))
    writeFileSync(join(outside, "secret.txt"), "leak")
    symlinkSync(join(outside, "secret.txt"), join(root, "link.txt"))
    const tool = makeReadFileTool({ workspaceRoot: root })
    const result = await runTool(tool, { path: "link.txt" }, { timeoutMs: 1000 })
    expect(result.ok).toBe(false)
    rmSync(outside, { recursive: true, force: true })
  })
})

describe("makeRunCommandTool", () => {
  let root: string

  afterEach(() => {
    if (root) rmSync(root, { recursive: true, force: true })
  })

  it("runs pwd inside the workspace", async () => {
    root = mkdtempSync(join(tmpdir(), "ws-tools-"))
    const tool = makeRunCommandTool({ workspaceRoot: root })
    const result = await runTool(tool, { argv: ["pwd"] }, { timeoutMs: 2000 })
    expect(result.ok).toBe(true)
    if (result.ok) expect(String(result.output).trim()).toBe(root)
  })

  it("rejects a program not on the allowlist", async () => {
    root = mkdtempSync(join(tmpdir(), "ws-tools-"))
    const tool = makeRunCommandTool({ workspaceRoot: root })
    const result = await runTool(tool, { argv: ["rm", "-rf", "/"] }, { timeoutMs: 1000 })
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.reason).toMatch(/not allowed/)
  })

  it("rejects args that try to leave the workspace", async () => {
    root = mkdtempSync(join(tmpdir(), "ws-tools-"))
    mkdirSync(join(root, "sub"))
    const tool = makeRunCommandTool({ workspaceRoot: root })
    const result = await runTool(tool, { argv: ["cat", "../outside"] }, { timeoutMs: 1000 })
    expect(result.ok).toBe(false)
  })

  it("ALLOWED_RUN_COMMANDS is a closed list", () => {
    expect(ALLOWED_RUN_COMMANDS).toEqual([
      "cat",
      "date",
      "echo",
      "git",
      "grep",
      "head",
      "ls",
      "node",
      "pnpm",
      "pwd",
      "python3",
      "rg",
      "wc",
    ])
    expect(ALLOWED_RUN_COMMANDS).not.toContain("rm")
    expect(ALLOWED_RUN_COMMANDS).not.toContain("bash")
    expect(ALLOWED_RUN_COMMANDS).not.toContain("sh")
    expect(ALLOWED_RUN_COMMANDS).not.toContain("curl")
    expect(ALLOWED_RUN_COMMANDS).not.toContain("sudo")
  })

  it("runs python3, node, pnpm, and grep inside the workspace", async () => {
    root = mkdtempSync(join(tmpdir(), "ws-tools-"))
    writeFileSync(join(root, "needle.txt"), "find-me-butler")
    const tool = makeRunCommandTool({ workspaceRoot: root })
    const py = await runTool(tool, { argv: ["python3", "-c", "print(42)"] }, { timeoutMs: 5000 })
    expect(py.ok).toBe(true)
    if (py.ok) expect(String(py.output).trim()).toBe("42")
    const node = await runTool(
      tool,
      { argv: ["node", "-e", "console.log(7)"] },
      { timeoutMs: 5000 },
    )
    expect(node.ok).toBe(true)
    if (node.ok) expect(String(node.output).trim()).toBe("7")
    const pnpm = await runTool(tool, { argv: ["pnpm", "--version"] }, { timeoutMs: 8000 })
    expect(pnpm.ok).toBe(true)
    const grep = await runTool(
      tool,
      { argv: ["grep", "find-me-butler", "needle.txt"] },
      { timeoutMs: 2000 },
    )
    expect(grep.ok).toBe(true)
    if (grep.ok) expect(String(grep.output)).toContain("find-me-butler")
    const rg = await runTool(tool, { argv: ["rg", "--version"] }, { timeoutMs: 2000 })
    expect(rg.ok).toBe(true)
  })

  it("still rejects banned programs after the named expand", async () => {
    root = mkdtempSync(join(tmpdir(), "ws-tools-"))
    const tool = makeRunCommandTool({ workspaceRoot: root })
    for (const program of ["bash", "curl", "chmod", "wget"]) {
      const result = await runTool(tool, { argv: [program] }, { timeoutMs: 1000 })
      expect(result.ok).toBe(false)
    }
  })
})
