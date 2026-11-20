import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import type { AgentTool } from "@butler/pi-agent"
import { createPiNativeTools, resolveInsideWorkspace } from "./pi-native-tools.js"

let root: string
let outside: string

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "pi-tools-"))
  outside = mkdtempSync(join(tmpdir(), "pi-outside-"))
})

afterEach(() => {
  rmSync(root, { recursive: true, force: true })
  rmSync(outside, { recursive: true, force: true })
})

function tool(tools: readonly AgentTool[], name: string): AgentTool {
  const found = tools.find((entry) => entry.name === name)
  if (!found) throw new Error(`missing tool: ${name}`)
  return found
}

function textOf(result: { content: readonly { type: string; text?: string }[] }): string {
  return result.content.map((block) => (block.type === "text" ? (block.text ?? "") : "")).join("")
}

async function call(
  tools: readonly AgentTool[],
  name: string,
  args: Record<string, unknown>,
  signal?: AbortSignal,
) {
  return tool(tools, name).execute("call-1", args, signal)
}

describe("resolveInsideWorkspace", () => {
  it("allows relative and absolute paths inside the workspace", async () => {
    writeFileSync(join(root, "a.txt"), "a")
    expect(await resolveInsideWorkspace(root, "a.txt")).toMatchObject({ ok: true })
    expect(await resolveInsideWorkspace(root, join(root, "a.txt"))).toMatchObject({ ok: true })
  })

  it("rejects parent traversal and absolute paths outside", async () => {
    expect((await resolveInsideWorkspace(root, "../escape.txt")).ok).toBe(false)
    expect((await resolveInsideWorkspace(root, "/etc/passwd")).ok).toBe(false)
  })

  it("rejects a symlink that points outside the workspace", async () => {
    writeFileSync(join(outside, "secret.txt"), "secret")
    symlinkSync(join(outside, "secret.txt"), join(root, "link.txt"))
    expect((await resolveInsideWorkspace(root, "link.txt")).ok).toBe(false)
  })

  it("rejects a dangling symlink", async () => {
    symlinkSync(join(outside, "missing.txt"), join(root, "dangling.txt"))
    expect((await resolveInsideWorkspace(root, "dangling.txt")).ok).toBe(false)
  })
})

describe("native tools stay inside the workspace", () => {
  it("does not read through an out-of-workspace symlink", async () => {
    writeFileSync(join(outside, "secret.txt"), "secret")
    symlinkSync(join(outside, "secret.txt"), join(root, "link.txt"))

    const result = await call(createPiNativeTools({ cwd: root }), "read", { path: "link.txt" })
    expect(result.isError).toBe(true)
    expect(textOf(result)).not.toContain("secret")
  })

  it("does not write through a dangling symlink", async () => {
    symlinkSync(join(outside, "new.txt"), join(root, "dangling.txt"))

    const result = await call(createPiNativeTools({ cwd: root }), "write", {
      path: "dangling.txt",
      content: "x",
    })
    expect(result.isError).toBe(true)
    expect(existsSync(join(outside, "new.txt"))).toBe(false)
  })

  it("does not create directories through a dangling symlink parent", async () => {
    symlinkSync(join(outside, "dir"), join(root, "dangling-dir"))

    const result = await call(createPiNativeTools({ cwd: root }), "write", {
      path: "dangling-dir/new.txt",
      content: "x",
    })
    expect(result.isError).toBe(true)
    expect(existsSync(join(outside, "dir"))).toBe(false)
  })

  it("creates new nested directories inside the workspace", async () => {
    const result = await call(createPiNativeTools({ cwd: root }), "write", {
      path: "a/b/c.txt",
      content: "ok",
    })
    expect(result.isError).toBe(false)
    expect(readFileSync(join(root, "a/b/c.txt"), "utf8")).toBe("ok")
  })

  it("does not follow symlinks while searching", async () => {
    mkdirSync(join(outside, "sub"))
    writeFileSync(join(outside, "sub", "x.ts"), "export {}")
    symlinkSync(join(outside, "sub"), join(root, "escape"))

    const result = await call(createPiNativeTools({ cwd: root }), "find", {
      pattern: "**/*.ts",
    })
    expect(textOf(result)).not.toContain("escape")
  })
})

describe("resource limits", () => {
  it("rejects oversized reads and writes but keeps the run usable", async () => {
    const tools = createPiNativeTools({ cwd: root, maxReadBytes: 8, maxWriteBytes: 8 })
    writeFileSync(join(root, "big.txt"), "0123456789")
    writeFileSync(join(root, "small.txt"), "ok")

    expect((await call(tools, "read", { path: "big.txt" })).isError).toBe(true)
    expect((await call(tools, "write", { path: "new.txt", content: "0123456789" })).isError).toBe(
      true,
    )
    expect((await call(tools, "read", { path: "small.txt" })).isError).toBe(false)
  })

  it("truncates bash output at the configured limit", async () => {
    const tools = createPiNativeTools({ cwd: root, maxOutputBytes: 16 })
    const result = await call(tools, "bash", { command: "printf abcdefghijklmnopqrstuvwxyz" })
    expect(result.isError).toBe(false)
    expect(textOf(result)).toContain("truncated")
  })
})

describe("bash containment", () => {
  it("times out and reports an error", async () => {
    const tools = createPiNativeTools({ cwd: root, timeoutMs: 100 })
    const result = await call(tools, "bash", { command: "sleep 5" })
    expect(result.isError).toBe(true)
    expect(textOf(result)).toMatch(/timeout/)
  }, 3_000)

  it("kills the process when the tool signal aborts", async () => {
    const tools = createPiNativeTools({ cwd: root })
    const controller = new AbortController()
    const pending = call(tools, "bash", { command: "sleep 5" }, controller.signal)
    setTimeout(() => controller.abort(), 50)

    const result = await pending
    expect(result.isError).toBe(true)
    expect(textOf(result)).toContain("aborted")
  }, 3_000)

  it("only exposes whitelisted and explicitly injected env vars", async () => {
    process.env["WFXM_TEST_SECRET"] = "leak"
    try {
      const tools = createPiNativeTools({ cwd: root })
      const result = await call(tools, "bash", {
        command: 'printf "%s|%s" "${WFXM_TEST_SECRET:-none}" "${INJECTED:-none}"',
      })
      expect(textOf(result)).toBe("none|none")
    } finally {
      delete process.env["WFXM_TEST_SECRET"]
    }
  })

  it("passes explicitly injected env vars", async () => {
    const tools = createPiNativeTools({ cwd: root, env: { INJECTED: "yes" } })
    const result = await call(tools, "bash", { command: 'printf "%s" "${INJECTED:-none}"' })
    expect(textOf(result)).toBe("yes")
  })
})

describe("tool protocol", () => {
  it("exposes the seven pi-shaped tools with non-empty results", async () => {
    const tools = createPiNativeTools({ cwd: root })
    expect(tools.map((entry) => entry.name).sort()).toEqual([
      "bash",
      "edit",
      "find",
      "grep",
      "ls",
      "read",
      "write",
    ])

    writeFileSync(join(root, "a.txt"), "hello\n")
    const results = [
      await call(tools, "read", { path: "a.txt" }),
      await call(tools, "write", { path: "b.txt", content: "b" }),
      await call(tools, "edit", { path: "b.txt", oldText: "b", newText: "bb" }),
      await call(tools, "bash", { command: "printf ok" }),
      await call(tools, "grep", { pattern: "hello" }),
      await call(tools, "find", { pattern: "*.txt" }),
      await call(tools, "ls", { path: "." }),
    ]
    for (const result of results) {
      expect(result.isError).toBe(false)
      expect(textOf(result).length).toBeGreaterThan(0)
    }
  })

  it("returns failures as isError results and keeps working", async () => {
    const tools = createPiNativeTools({ cwd: root })

    const missing = await call(tools, "read", { path: "missing.txt" })
    expect(missing.isError).toBe(true)
    expect(textOf(missing)).toContain("error")

    const badGrep = await call(tools, "grep", { pattern: "(" })
    expect(badGrep.isError).toBe(true)

    writeFileSync(join(root, "ok.txt"), "ok")
    const works = await call(tools, "read", { path: "ok.txt" })
    expect(works.isError).toBe(false)
    expect(textOf(works)).toContain("ok")
  })
})
