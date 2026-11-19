/**
 * R8.x.12 — sandbox path + argv helpers for read_file / run_command.
 */
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { runTool } from "@butler/runtime/tool-runtime.js"
import type { CredentialProvider } from "@butler/ports/core/credential-provider.js"
import { makeListDirTool, makeRunCommandTool } from "./workspace-tools.js"

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
})
