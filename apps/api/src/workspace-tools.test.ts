/**
 * R8.x.12 — sandbox path + argv helpers for read_file / run_command.
 */
import { mkdtempSync, mkdirSync, existsSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { runTool } from "@butler/runtime/tool-runtime.js"
import type { CredentialProvider } from "@butler/ports/core/credential-provider.js"
import {
  makeEditFileTool,
  makeListDirTool,
  makeReadFileTool,
  makeRunCommandTool,
} from "./workspace-tools.js"

const fakeProvider = (values: Readonly<Record<string, string>>): CredentialProvider => ({
  availableCredentials: async () => Object.keys(values),
  resolveCredentials: async (names) => {
    const out: Record<string, string> = {}
    for (const n of names) {
      if (!(n in values)) throw new Error(`credential not resolvable: ${n}`)
      out[n] = values[n]
    }
    return out
  },
})

describe("makeListDirTool", () => {
  let root: string

  afterEach(() => {
    if (root) rmSync(root, { recursive: true, force: true })
  })

  it("lists directories before files and hides node_modules", async () => {
    root = mkdtempSync(join(tmpdir(), "ws-list-"))
    mkdirSync(join(root, "packages"))
    mkdirSync(join(root, "node_modules"))
    writeFileSync(join(root, "a.txt"), "x")
    const result = await runTool(makeListDirTool({ workspaceRoot: root }), {}, { timeoutMs: 1000 })
    expect(result.ok).toBe(true)
    if (!result.ok) return
    const output = String(result.output)
    expect(output).toContain("[目录] packages")
    expect(output).toContain("a.txt")
    expect(output).not.toContain("node_modules")
    expect(output.indexOf("packages")).toBeLessThan(output.indexOf("a.txt"))
  })
})

describe("makeReadFileTool", () => {
  let root: string
  let prevSandbox: string | undefined

  beforeEach(() => {
    prevSandbox = process.env["BUTLER_V5_SANDBOX"]
    delete process.env["BUTLER_V5_SANDBOX"]
  })

  afterEach(() => {
    if (root) rmSync(root, { recursive: true, force: true })
    if (prevSandbox === undefined) delete process.env["BUTLER_V5_SANDBOX"]
    else process.env["BUTLER_V5_SANDBOX"] = prevSandbox
  })

  it("F13: supports offset/limit paging for large files", async () => {
    root = mkdtempSync(join(tmpdir(), "ws-read-"))
    const lines = Array.from({ length: 600 }, (_, i) => `line-${i + 1}`)
    writeFileSync(join(root, "big.txt"), lines.join("\n"))
    const tool = makeReadFileTool({ workspaceRoot: root })

    const page = await runTool(tool, { path: "big.txt", offset: 101, limit: 3 }, { timeoutMs: 2000 })
    expect(page.ok).toBe(true)
    if (!page.ok) return
    const text = String(page.output)
    expect(text).toContain("lines 101-103 of 600")
    expect(text).toContain("line-101")
    expect(text).toContain("line-103")
    expect(text).not.toContain("line-104")

    const whole = await runTool(tool, { path: "big.txt" }, { timeoutMs: 2000 })
    expect(whole.ok).toBe(true)
    if (whole.ok) expect(String(whole.output)).toContain("line-600")
  })

  it("F13: caps inline output at 24KiB with a paging hint", async () => {
    root = mkdtempSync(join(tmpdir(), "ws-read-"))
    writeFileSync(join(root, "huge.txt"), "x".repeat(30 * 1024))
    const tool = makeReadFileTool({ workspaceRoot: root })
    const result = await runTool(tool, { path: "huge.txt" }, { timeoutMs: 2000 })
    expect(result.ok).toBe(true)
    if (!result.ok) return
    const text = String(result.output)
    expect(text).toContain("输出已截断")
    expect(Buffer.byteLength(text, "utf8")).toBeLessThan(30 * 1024)
  })

  it("F21: reads files above 64KiB instead of refusing them", async () => {
    root = mkdtempSync(join(tmpdir(), "ws-read-"))
    const lines = Array.from({ length: 4000 }, (_, i) => `line-${i + 1}-${"y".repeat(20)}`)
    writeFileSync(join(root, "big-source.tsx"), lines.join("\n"))
    expect(readFileSync(join(root, "big-source.tsx")).byteLength).toBeGreaterThan(64 * 1024)
    const tool = makeReadFileTool({ workspaceRoot: root })
    const head = await runTool(tool, { path: "big-source.tsx" }, { timeoutMs: 2000 })
    expect(head.ok).toBe(true)
    if (!head.ok) return
    expect(String(head.output)).toContain("请用 offset/limit 继续读取")

    const page = await runTool(
      tool,
      { path: "big-source.tsx", offset: 3998, limit: 3 },
      { timeoutMs: 2000 },
    )
    expect(page.ok).toBe(true)
    if (page.ok) expect(String(page.output)).toContain("line-4000")
  })
})

describe("makeEditFileTool", () => {
  let root: string
  let prevSandbox: string | undefined

  beforeEach(() => {
    prevSandbox = process.env["BUTLER_V5_SANDBOX"]
    delete process.env["BUTLER_V5_SANDBOX"]
  })

  afterEach(() => {
    if (root) rmSync(root, { recursive: true, force: true })
    if (prevSandbox === undefined) delete process.env["BUTLER_V5_SANDBOX"]
    else process.env["BUTLER_V5_SANDBOX"] = prevSandbox
  })

  it("F14: replaces a unique snippet without touching the rest of the file", async () => {
    root = mkdtempSync(join(tmpdir(), "ws-edit-"))
    writeFileSync(join(root, "page.tsx"), "line-1\nOLD\ntail-keep\n")
    const tool = makeEditFileTool({ workspaceRoot: root })
    const result = await runTool(
      tool,
      { path: "page.tsx", oldText: "OLD", newText: "NEW" },
      { timeoutMs: 2000 },
    )
    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(String(result.output)).toContain("1 replacement(s)")
    const after = readFileSync(join(root, "page.tsx"), "utf8")
    expect(after).toBe("line-1\nNEW\ntail-keep\n")
  })

  it("F14: rejects an ambiguous snippet unless replaceAll is set", async () => {
    root = mkdtempSync(join(tmpdir(), "ws-edit-"))
    writeFileSync(join(root, "dup.txt"), "A\nA\nB\n")
    const tool = makeEditFileTool({ workspaceRoot: root })
    const ambiguous = await runTool(
      tool,
      { path: "dup.txt", oldText: "A", newText: "Z" },
      { timeoutMs: 2000 },
    )
    expect(ambiguous.ok).toBe(false)
    if (!ambiguous.ok) expect(ambiguous.reason).toContain("2 places")

    const all = await runTool(
      tool,
      { path: "dup.txt", oldText: "A", newText: "Z", replaceAll: true },
      { timeoutMs: 2000 },
    )
    expect(all.ok).toBe(true)
    expect(readFileSync(join(root, "dup.txt"), "utf8")).toBe("Z\nZ\nB\n")
  })

  it("F14: reports a clear error when oldText or the file is missing", async () => {
    root = mkdtempSync(join(tmpdir(), "ws-edit-"))
    writeFileSync(join(root, "x.txt"), "hello\n")
    const tool = makeEditFileTool({ workspaceRoot: root })
    const missing = await runTool(
      tool,
      { path: "x.txt", oldText: "nope", newText: "y" },
      { timeoutMs: 2000 },
    )
    expect(missing.ok).toBe(false)
    if (!missing.ok) expect(missing.reason).toContain("oldText not found")

    const noFile = await runTool(
      tool,
      { path: "ghost.txt", oldText: "a", newText: "b" },
      { timeoutMs: 2000 },
    )
    expect(noFile.ok).toBe(false)
  })

  it("F21: edits a file above the 64KiB write cap", async () => {
    root = mkdtempSync(join(tmpdir(), "ws-edit-"))
    const filler = Array.from({ length: 4000 }, (_, i) => `const row${i + 1} = ${i + 1}`).join("\n")
    writeFileSync(join(root, "page.tsx"), `${filler}\nconst MARKER = "old"\n`)
    expect(readFileSync(join(root, "page.tsx")).byteLength).toBeGreaterThan(64 * 1024)
    const tool = makeEditFileTool({ workspaceRoot: root })
    const result = await runTool(
      tool,
      { path: "page.tsx", oldText: 'const MARKER = "old"', newText: 'const MARKER = "new"' },
      { timeoutMs: 2000 },
    )
    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(String(result.output)).toContain("1 replacement(s)")
    expect(readFileSync(join(root, "page.tsx"), "utf8")).toContain('const MARKER = "new"')
  })
})

describe("makeRunCommandTool", () => {
  let root: string
  let prevSandbox: string | undefined

  beforeEach(() => {
    // Host env may set bubblewrap; nvm node/pnpm are not visible inside bwrap ro-bind.
    prevSandbox = process.env["BUTLER_V5_SANDBOX"]
    delete process.env["BUTLER_V5_SANDBOX"]
  })

  afterEach(() => {
    if (root) rmSync(root, { recursive: true, force: true })
    if (prevSandbox === undefined) delete process.env["BUTLER_V5_SANDBOX"]
    else process.env["BUTLER_V5_SANDBOX"] = prevSandbox
  })

  it("P2: run_command fails closed when a requested credential is not host-authorized", async () => {
    root = mkdtempSync(join(tmpdir(), "ws-tools-"))
    const tool = makeRunCommandTool({
      workspaceRoot: root,
      credentialProvider: fakeProvider({ REGISTRY_TOKEN: "secret" }),
      credentialAllowlist: ["OTHER_TOKEN"],
    })
    const result = await runTool(
      tool,
      { argv: ["pwd"], credentials: ["REGISTRY_TOKEN"] },
      { timeoutMs: 2000 },
    )
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.reason).toMatch(/not authorized/)
  })

  it("P2: authorized credential value reaches the child command env (not in args)", async () => {
    root = mkdtempSync(join(tmpdir(), "ws-tools-"))
    const provider = fakeProvider({ REGISTRY_TOKEN: "sec-value-123" })
    const tool = makeRunCommandTool({
      workspaceRoot: root,
      credentialProvider: provider,
      credentialAllowlist: ["REGISTRY_TOKEN"],
    })
    const result = await runTool(
      tool,
      {
        argv: ["node", "-e", "console.log(process.env.REGISTRY_TOKEN || 'unset')"],
        credentials: ["REGISTRY_TOKEN"],
      },
      { timeoutMs: 5000 },
    )
    expect(result.ok).toBe(true)
    if (result.ok) expect(String(result.output).trim()).toBe("sec-value-123")
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

  it("F18: timeout kills the whole process tree, including grandchildren", async () => {
    root = mkdtempSync(join(tmpdir(), "ws-tools-"))
    const grandchildPidFile = join(root, "grandchild.pid")
    const tool = makeRunCommandTool({ workspaceRoot: root })
    // 父进程派生一个 30s 的孙进程并写 PID，然后自己也不退出：
    // 复刻 `pnpm build` → `sh -c next build` → node 的进程树形态。
    const script = [
      'const { spawn } = require("node:child_process")',
      'const { writeFileSync } = require("node:fs")',
      'const g = spawn("sleep", ["30"])',
      `writeFileSync(${JSON.stringify(grandchildPidFile)}, String(g.pid))`,
      "setTimeout(() => {}, 30000)",
    ].join("; ")

    const result = await runTool(tool, { argv: ["node", "-e", script] }, { timeoutMs: 1500 })
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.reason).toMatch(/timeout/)
    expect(existsSync(grandchildPidFile)).toBe(true)

    const grandchildPid = Number(readFileSync(grandchildPidFile, "utf8").trim())
    expect(Number.isInteger(grandchildPid)).toBe(true)
    // 给 SIGKILL 一点送达时间，然后确认孙进程确实已退出（kill -0 抛 ESRCH）。
    await new Promise((resolve) => setTimeout(resolve, 500))
    let alive = true
    try {
      process.kill(grandchildPid, 0)
    } catch {
      alive = false
    }
    expect(alive).toBe(false)
  })
})
