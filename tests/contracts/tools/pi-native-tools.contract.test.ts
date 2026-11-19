// 锚定契约：pi-native 工具 read/write/edit/bash/grep/find/ls 的必填参数、返回结构、错误 envelope、路径边界与输出/超时预算。
import { mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { createPiNativeTools } from "../../../packages/runtime/src/execution/pi-native-tools.js"
import type { PiNativeToolOptions } from "../../../packages/runtime/src/execution/pi-native-tools.js"
import { READ_LIMIT_BYTES, makeEscapeSymlink, makeTempWorkspace } from "./tool-fixtures.js"
import type { TempWorkspace } from "./tool-fixtures.js"

let tmp: TempWorkspace

beforeEach(() => {
  tmp = makeTempWorkspace("pi-contract-")
})

afterEach(() => {
  tmp.cleanup()
})

type PiTools = ReturnType<typeof createPiNativeTools>
type PiToolResult = Awaited<ReturnType<PiTools[number]["execute"]>>

function build(overrides: Partial<PiNativeToolOptions> = {}): PiTools {
  return createPiNativeTools({ cwd: tmp.root, timeoutMs: 5000, ...overrides })
}

async function call(
  tools: PiTools,
  name: string,
  args: Record<string, unknown>,
): Promise<PiToolResult> {
  const tool = tools.find((entry) => entry.name === name)
  if (!tool) throw new Error(`missing tool ${name}`)
  return tool.execute(`contract-${name}`, args)
}

function textOf(result: PiToolResult): string {
  return result.content.map((part) => (part.type === "text" ? part.text : "")).join("\n")
}

interface EscapeCase {
  readonly label: string
  readonly path: string
}

/** bash 没有 path 参数（以 cwd 为边界），因此不在此矩阵内。 */
function escapeInputs(): EscapeCase[] {
  return [
    { label: "parent traversal", path: "../secret.txt" },
    { label: "absolute path", path: "/etc/passwd" },
    { label: "escaping symlink", path: "escape-link.txt" },
  ]
}

describe("pi native tools — required parameters", () => {
  const cases: { tool: string; args: Record<string, unknown>; fragment: string }[] = [
    { tool: "read", args: {}, fragment: "path is required" },
    { tool: "read", args: { path: 1 }, fragment: "path is required" },
    { tool: "write", args: { content: "x" }, fragment: "path is required" },
    { tool: "write", args: { path: "a.txt" }, fragment: "content is required" },
    { tool: "edit", args: { oldText: "a", newText: "b" }, fragment: "path is required" },
    { tool: "edit", args: { path: "a.txt", newText: "b" }, fragment: "oldText is required" },
    { tool: "edit", args: { path: "a.txt", oldText: "", newText: "b" }, fragment: "oldText is required" },
    { tool: "edit", args: { path: "a.txt", oldText: "a" }, fragment: "newText is required" },
    { tool: "bash", args: {}, fragment: "command is required" },
    { tool: "bash", args: { command: "   " }, fragment: "command is required" },
    { tool: "grep", args: {}, fragment: "pattern is required" },
    { tool: "find", args: {}, fragment: "pattern is required" },
  ]

  for (const tc of cases) {
    it(`${tc.tool}: ${JSON.stringify(tc.args)} → ${tc.fragment}`, async () => {
      const result = await call(build(), tc.tool, tc.args)
      expect(result.isError).toBe(true)
      expect(textOf(result)).toContain(tc.fragment)
    })
  }
})

describe("pi native read contract", () => {
  for (const tc of escapeInputs()) {
    it(`rejects ${tc.label}`, async () => {
      makeEscapeSymlink(tmp)
      const result = await call(build(), "read", { path: tc.path })
      expect(result.isError).toBe(true)
      expect(textOf(result)).toContain("outside the workspace")
    })
  }

  it("reads an empty file as an explicit empty marker (F-11)", async () => {
    writeFileSync(join(tmp.root, "empty.txt"), "", "utf8")
    const result = await call(build(), "read", { path: "empty.txt" })
    expect(result.isError).toBeFalsy()
    expect(result.details["bytes"]).toBe(0)
    expect(textOf(result)).toContain("(empty file)")
  })

  it("rejects binary content", async () => {
    writeFileSync(join(tmp.root, "bin.dat"), Buffer.from([0x61, 0x00, 0x62]))
    const result = await call(build(), "read", { path: "bin.dat" })
    expect(result.isError).toBe(true)
    expect(textOf(result)).toContain("refusing binary file")
  })

  it("rejects files above the 64KiB budget", async () => {
    writeFileSync(join(tmp.root, "big.txt"), Buffer.alloc(READ_LIMIT_BYTES + 1, 0x61))
    const result = await call(build(), "read", { path: "big.txt" })
    expect(result.isError).toBe(true)
    expect(textOf(result)).toContain(`file exceeds ${READ_LIMIT_BYTES} bytes`)
  })

  it("accepts a file exactly at the 64KiB budget", async () => {
    writeFileSync(join(tmp.root, "edge.txt"), Buffer.alloc(READ_LIMIT_BYTES, 0x61))
    const result = await call(build(), "read", { path: "edge.txt" })
    expect(result.isError).toBeFalsy()
    expect(result.details["bytes"]).toBe(READ_LIMIT_BYTES)
  })

  it("returns an error result for a missing file", async () => {
    const result = await call(build(), "read", { path: "missing.txt" })
    expect(result.isError).toBe(true)
    expect(textOf(result)).toMatch(/\[error\]/)
  })
})

describe("pi native write contract", () => {
  for (const tc of escapeInputs()) {
    it(`rejects ${tc.label}`, async () => {
      makeEscapeSymlink(tmp)
      const result = await call(build(), "write", { path: tc.path, content: "x" })
      expect(result.isError).toBe(true)
      expect(textOf(result)).toContain("outside the workspace")
    })
  }

  it("rejects content above the 64KiB budget", async () => {
    const result = await call(build(), "write", {
      path: "big.txt",
      content: "a".repeat(READ_LIMIT_BYTES + 1),
    })
    expect(result.isError).toBe(true)
    expect(textOf(result)).toContain(`content exceeds ${READ_LIMIT_BYTES} bytes`)
  })

  it("refuses binary content", async () => {
    const result = await call(build(), "write", { path: "bin.dat", content: "a\0b" })
    expect(result.isError).toBe(true)
    expect(textOf(result)).toContain("refusing binary content")
  })

  it("writes empty content", async () => {
    const result = await call(build(), "write", { path: "empty.txt", content: "" })
    expect(result.isError).toBeFalsy()
    expect(readFileSync(join(tmp.root, "empty.txt"), "utf8")).toBe("")
  })

  it("is idempotent and creates nested directories", async () => {
    const tools = build()
    const args = { path: "nested/deep/a.txt", content: "stable" }
    const first = await call(tools, "write", args)
    const second = await call(tools, "write", args)
    expect(first.isError).toBeFalsy()
    expect(second.isError).toBeFalsy()
    expect(readFileSync(join(tmp.root, "nested/deep/a.txt"), "utf8")).toBe("stable")
  })
})

describe("pi native edit contract", () => {
  it("returns an error result when oldText is absent", async () => {
    writeFileSync(join(tmp.root, "a.txt"), "hello", "utf8")
    const result = await call(build(), "edit", {
      path: "a.txt",
      oldText: "absent",
      newText: "x",
    })
    expect(result.isError).toBe(true)
    expect(textOf(result)).toContain("oldText was not found")
  })

  for (const tc of escapeInputs()) {
    it(`rejects ${tc.label}`, async () => {
      makeEscapeSymlink(tmp)
      const result = await call(build(), "edit", {
        path: tc.path,
        oldText: "a",
        newText: "b",
      })
      expect(result.isError).toBe(true)
      expect(textOf(result)).toContain("outside the workspace")
    })
  }

  it("allows an empty newText (deletion) when oldText matches once", async () => {
    writeFileSync(join(tmp.root, "a.txt"), "abc", "utf8")
    const result = await call(build(), "edit", { path: "a.txt", oldText: "b", newText: "" })
    expect(result.isError).toBeFalsy()
    expect(readFileSync(join(tmp.root, "a.txt"), "utf8")).toBe("ac")
  })
})

describe("pi native bash contract", () => {
  it("runs with the workspace as cwd", async () => {
    const result = await call(build(), "bash", { command: "pwd" })
    expect(result.isError).toBeFalsy()
    expect(textOf(result).trim()).toBe(tmp.root)
  })

  it("reports non-zero exits as an isError result (not a throw)", async () => {
    const result = await call(build(), "bash", { command: "exit 7" })
    expect(result.isError).toBe(true)
    expect(textOf(result)).toContain("exit 7")
    expect(result.details["exitCode"]).toBe(7)
  })

  it("truncates output at the configured budget with a marker", async () => {
    const result = await call(build({ maxOutputBytes: 64 }), "bash", {
      command: "printf '%0200d' 0",
    })
    expect(result.isError).toBeFalsy()
    expect(textOf(result)).toContain("truncated at 64 bytes")
  })

  it("honours the configured timeoutMs", async () => {
    const result = await call(build({ timeoutMs: 100 }), "bash", { command: "sleep 5" })
    expect(result.isError).toBe(true)
    expect(textOf(result)).toContain("timeout after 100ms")
  })
})

describe("pi native grep contract", () => {
  for (const tc of escapeInputs()) {
    it(`rejects ${tc.label}`, async () => {
      makeEscapeSymlink(tmp)
      const result = await call(build(), "grep", { pattern: "x", path: tc.path })
      expect(result.isError).toBe(true)
      expect(textOf(result)).toContain("outside the workspace")
    })
  }

  it("returns the no-matches marker", async () => {
    writeFileSync(join(tmp.root, "a.txt"), "alpha", "utf8")
    const result = await call(build(), "grep", { pattern: "needle" })
    expect(result.isError).toBeFalsy()
    expect(textOf(result)).toBe("no matches")
  })

  it("returns an error result for an invalid regex", async () => {
    const result = await call(build(), "grep", { pattern: "[" })
    expect(result.isError).toBe(true)
    expect(textOf(result)).toContain("invalid pattern")
  })
})

describe("pi native find contract", () => {
  for (const tc of escapeInputs()) {
    it(`rejects ${tc.label}`, async () => {
      makeEscapeSymlink(tmp)
      const result = await call(build(), "find", { pattern: "*", path: tc.path })
      expect(result.isError).toBe(true)
      expect(textOf(result)).toContain("outside the workspace")
    })
  }

  it("returns the no-files marker", async () => {
    writeFileSync(join(tmp.root, "a.ts"), "x", "utf8")
    const result = await call(build(), "find", { pattern: "*.zzz" })
    expect(result.isError).toBeFalsy()
    expect(textOf(result)).toBe("no files")
  })
})

describe("pi native ls contract", () => {
  it("returns the empty marker for an empty directory", async () => {
    mkdirSync(join(tmp.root, "empty"))
    const result = await call(build(), "ls", { path: "empty" })
    expect(result.isError).toBeFalsy()
    expect(textOf(result)).toBe("(empty directory)")
  })

  it("returns an error result for a missing directory", async () => {
    const result = await call(build(), "ls", { path: "nope" })
    expect(result.isError).toBe(true)
  })

  it("returns an error result for a file path", async () => {
    writeFileSync(join(tmp.root, "a.txt"), "x", "utf8")
    const result = await call(build(), "ls", { path: "a.txt" })
    expect(result.isError).toBe(true)
  })

  for (const tc of escapeInputs()) {
    it(`rejects ${tc.label}`, async () => {
      makeEscapeSymlink(tmp)
      const result = await call(build(), "ls", { path: tc.path })
      expect(result.isError).toBe(true)
      expect(textOf(result)).toContain("outside the workspace")
    })
  }
})
