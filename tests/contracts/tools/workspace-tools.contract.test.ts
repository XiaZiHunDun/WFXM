// 锚定契约：workspace-tools 的入参校验、返回结构、错误 envelope、路径边界与字节预算（list_dir/read_file/write_file/run_command/send_wechat_file）。
import { existsSync, mkdirSync, readFileSync } from "node:fs"
import { join } from "node:path"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { runTool } from "../../../packages/runtime/src/tool-runtime.js"
import type { RunOutcome, ToolDefinition } from "../../../packages/runtime/src/tool-runtime.js"
import {
  makeListDirTool,
  makeReadFileTool,
  makeRunCommandTool,
  makeWriteFileTool,
  validateRunCommandArgs,
} from "../../../apps/api/src/workspace-tools.js"
import { makeSendWechatFileTool } from "../../../apps/api/src/send-wechat-file.js"
import type { SendWechatFileContext } from "../../../apps/api/src/send-wechat-file.js"
import {
  COMMAND_OUTPUT_LIMIT_BYTES,
  READ_LIMIT_BYTES,
  makeEscapeSymlink,
  makeTempWorkspace,
  writeBytes,
  writeText,
} from "./tool-fixtures.js"
import type { TempWorkspace } from "./tool-fixtures.js"

let tmp: TempWorkspace
let prevSandbox: string | undefined

beforeEach(() => {
  tmp = makeTempWorkspace("ws-contract-")
  // 契约测试固定走进程内 fs/spawn 路径；宿主机若开 bwrap 会改变错误文本。
  prevSandbox = process.env["BUTLER_V5_SANDBOX"]
  delete process.env["BUTLER_V5_SANDBOX"]
})

afterEach(() => {
  tmp.cleanup()
  if (prevSandbox === undefined) delete process.env["BUTLER_V5_SANDBOX"]
  else process.env["BUTLER_V5_SANDBOX"] = prevSandbox
})

async function call(
  tool: ToolDefinition,
  args: Record<string, unknown>,
  timeoutMs = 5000,
): Promise<RunOutcome> {
  return runTool(tool, args, { timeoutMs })
}

function reasonOf(result: RunOutcome): string {
  return result.ok ? "" : result.reason
}

function outputOf(result: RunOutcome): string {
  return result.ok ? String(result.output) : ""
}

interface PathCase {
  readonly label: string
  readonly path: string
}

function escapeCases(): PathCase[] {
  return [
    { label: "parent traversal", path: "../secret.txt" },
    { label: "absolute path", path: "/etc/passwd" },
    { label: "escaping symlink", path: "escape-link.txt" },
  ]
}

describe("list_dir contract", () => {
  it("defaults to the workspace root when path is absent", async () => {
    writeText(tmp.root, "a.txt", "x")
    const result = await call(makeListDirTool({ workspaceRoot: tmp.root }), {})
    expect(result.ok).toBe(true)
    expect(outputOf(result)).toContain("a.txt")
  })

  it("returns the empty marker for an empty directory", async () => {
    mkdirSync(join(tmp.root, "empty"))
    const result = await call(makeListDirTool({ workspaceRoot: tmp.root }), { path: "empty" })
    expect(result.ok).toBe(true)
    expect(outputOf(result)).toBe("(empty)")
  })

  for (const tc of escapeCases()) {
    it(`rejects ${tc.label}`, async () => {
      makeEscapeSymlink(tmp)
      const result = await call(makeListDirTool({ workspaceRoot: tmp.root }), { path: tc.path })
      expect(result.ok).toBe(false)
      expect(reasonOf(result)).toMatch(/outside the workspace/)
    })
  }
})

describe("read_file contract", () => {
  it("requires a string path", async () => {
    const tool = makeReadFileTool({ workspaceRoot: tmp.root })
    for (const args of [{}, { path: 42 }]) {
      const result = await call(tool, args)
      expect(result.ok).toBe(false)
      expect(reasonOf(result)).toBe("path is required")
    }
  })

  for (const tc of escapeCases()) {
    it(`rejects ${tc.label}`, async () => {
      makeEscapeSymlink(tmp)
      const result = await call(makeReadFileTool({ workspaceRoot: tmp.root }), { path: tc.path })
      expect(result.ok).toBe(false)
      expect(reasonOf(result)).toMatch(/outside the workspace/)
    })
  }

  it("refuses binary content", async () => {
    writeBytes(tmp.root, "bin.dat", Buffer.from([0x61, 0x00, 0x62]))
    const result = await call(makeReadFileTool({ workspaceRoot: tmp.root }), { path: "bin.dat" })
    expect(result.ok).toBe(false)
    expect(reasonOf(result)).toBe("refusing binary file")
  })

  it("rejects files above the 64KiB budget", async () => {
    writeBytes(tmp.root, "big.txt", Buffer.alloc(READ_LIMIT_BYTES + 1, 0x61))
    const result = await call(makeReadFileTool({ workspaceRoot: tmp.root }), { path: "big.txt" })
    expect(result.ok).toBe(false)
    expect(reasonOf(result)).toContain(`file exceeds ${READ_LIMIT_BYTES} bytes`)
  })

  it("returns empty output for an empty file", async () => {
    writeText(tmp.root, "empty.txt", "")
    const result = await call(makeReadFileTool({ workspaceRoot: tmp.root }), { path: "empty.txt" })
    expect(result.ok).toBe(true)
    expect(outputOf(result)).toBe("")
  })

  it("rejects a directory path", async () => {
    mkdirSync(join(tmp.root, "dir"))
    const result = await call(makeReadFileTool({ workspaceRoot: tmp.root }), { path: "dir" })
    expect(result.ok).toBe(false)
    expect(reasonOf(result)).toBe("path is not a file")
  })

  it("returns a failure envelope for a missing file", async () => {
    const result = await call(makeReadFileTool({ workspaceRoot: tmp.root }), { path: "missing.txt" })
    expect(result.ok).toBe(false)
    expect(reasonOf(result).length).toBeGreaterThan(0)
  })
})

describe("write_file contract", () => {
  const requiredCases: {
    label: string
    args: Record<string, unknown>
    reason: string
  }[] = [
    { label: "missing path", args: { content: "x" }, reason: "path is required" },
    { label: "missing content", args: { path: "a.txt" }, reason: "content is required" },
    { label: "non-string content", args: { path: "a.txt", content: 5 }, reason: "content is required" },
  ]

  for (const tc of requiredCases) {
    it(`rejects ${tc.label}`, async () => {
      const result = await call(makeWriteFileTool({ workspaceRoot: tmp.root }), tc.args)
      expect(result.ok).toBe(false)
      expect(reasonOf(result)).toBe(tc.reason)
    })
  }

  for (const tc of escapeCases()) {
    it(`rejects ${tc.label}`, async () => {
      makeEscapeSymlink(tmp)
      const result = await call(makeWriteFileTool({ workspaceRoot: tmp.root }), {
        path: tc.path,
        content: "x",
      })
      expect(result.ok).toBe(false)
      expect(reasonOf(result)).toMatch(/outside the workspace/)
    })
  }

  it("rejects content above the 64KiB budget", async () => {
    const result = await call(makeWriteFileTool({ workspaceRoot: tmp.root }), {
      path: "big.txt",
      content: "a".repeat(READ_LIMIT_BYTES + 1),
    })
    expect(result.ok).toBe(false)
    expect(reasonOf(result)).toContain(`content exceeds ${READ_LIMIT_BYTES} bytes`)
  })

  it("refuses binary content", async () => {
    const result = await call(makeWriteFileTool({ workspaceRoot: tmp.root }), {
      path: "bin.dat",
      content: "a\0b",
    })
    expect(result.ok).toBe(false)
    expect(reasonOf(result)).toBe("refusing binary content")
  })

  it("writes empty content and creates nested directories", async () => {
    const result = await call(makeWriteFileTool({ workspaceRoot: tmp.root }), {
      path: "nested/deep/empty.txt",
      content: "",
    })
    expect(result.ok).toBe(true)
    expect(existsSync(join(tmp.root, "nested/deep/empty.txt"))).toBe(true)
    expect(readFileSync(join(tmp.root, "nested/deep/empty.txt"), "utf8")).toBe("")
  })

  it("is idempotent for repeated identical writes", async () => {
    const tool = makeWriteFileTool({ workspaceRoot: tmp.root })
    const args = { path: "same.txt", content: "stable" }
    const first = await call(tool, args)
    const second = await call(tool, args)
    expect(first.ok).toBe(true)
    expect(second.ok).toBe(true)
    expect(readFileSync(join(tmp.root, "same.txt"), "utf8")).toBe("stable")
  })
})

describe("run_command contract", () => {
  const validateCases: {
    label: string
    args: Record<string, unknown>
    fragment: string
  }[] = [
    { label: "missing argv", args: {}, fragment: "argv is required" },
    { label: "empty argv", args: { argv: [] }, fragment: "argv is required" },
    { label: "non-array argv", args: { argv: "ls" }, fragment: "argv is required" },
    { label: "non-string entry", args: { argv: ["ls", 5] }, fragment: "non-empty strings" },
    { label: "slash program", args: { argv: ["./ls"] }, fragment: "bare command name" },
    { label: "non-allowlisted program", args: { argv: ["rm", "-rf", "x"] }, fragment: "not allowed" },
    { label: "arg with parent traversal", args: { argv: ["cat", "../x"] }, fragment: "outside the workspace" },
    { label: "absolute arg", args: { argv: ["cat", "/etc/passwd"] }, fragment: "outside the workspace" },
  ]

  for (const tc of validateCases) {
    it(`validateRunCommandArgs rejects ${tc.label}`, () => {
      const parsed = validateRunCommandArgs(tc.args)
      expect(parsed.ok).toBe(false)
      if (!parsed.ok) expect(parsed.reason).toContain(tc.fragment)
    })
  }

  it("validateRunCommandArgs accepts an allowlisted bare program", () => {
    const parsed = validateRunCommandArgs({ argv: ["echo", "hi"] })
    expect(parsed.ok).toBe(true)
    if (parsed.ok) expect(parsed.argv).toEqual(["echo", "hi"])
  })

  it("runs an allowlisted command and returns its stdout", async () => {
    const result = await call(makeRunCommandTool({ workspaceRoot: tmp.root }), {
      argv: ["echo", "hello-contract"],
    })
    expect(result.ok).toBe(true)
    expect(outputOf(result)).toContain("hello-contract")
  })

  it("returns an error envelope for validation failures", async () => {
    const result = await call(makeRunCommandTool({ workspaceRoot: tmp.root }), {})
    expect(result.ok).toBe(false)
    expect(reasonOf(result)).toContain("argv is required")
  })

  it("rejects a non-allowlisted program", async () => {
    const result = await call(makeRunCommandTool({ workspaceRoot: tmp.root }), {
      argv: ["rm", "-rf", "."],
    })
    expect(result.ok).toBe(false)
    expect(reasonOf(result)).toContain("not allowed")
  })

  it("rejects arguments that escape the workspace", async () => {
    const tool = makeRunCommandTool({ workspaceRoot: tmp.root })
    for (const argv of [["cat", "../x"], ["cat", "/etc/passwd"]]) {
      const result = await call(tool, { argv })
      expect(result.ok).toBe(false)
      expect(reasonOf(result)).toContain("outside the workspace")
    }
  })

  it("returns exitCode (and does not throw) on a non-zero exit", async () => {
    const result = await call(
      makeRunCommandTool({ workspaceRoot: tmp.root }),
      { argv: ["node", "-e", "process.exit(3)"] },
      8000,
    )
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.exitCode).toBe(3)
      expect(result.reason).toContain("exit 3")
    }
  })

  it("truncates output at the 32KiB budget with a marker", async () => {
    const result = await call(
      makeRunCommandTool({ workspaceRoot: tmp.root }),
      { argv: ["node", "-e", "process.stdout.write('x'.repeat(40000))"] },
      8000,
    )
    expect(result.ok).toBe(true)
    expect(outputOf(result)).toContain(
      `truncated at ${COMMAND_OUTPUT_LIMIT_BYTES} bytes`,
    )
  })
})

describe("send_wechat_file contract", () => {
  interface CapturedSend {
    readonly to: string
    readonly fileName: string
    readonly plaintext: Buffer
    readonly caption?: string
  }

  function context(overrides: Partial<SendWechatFileContext> = {}): SendWechatFileContext {
    return {
      workspaceRoot: tmp.root,
      wechatUserId: "user-1",
      env: {},
      ...overrides,
    }
  }

  it("requires a wechat recipient", async () => {
    writeText(tmp.root, "a.txt", "x")
    const result = await call(
      makeSendWechatFileTool({ workspaceRoot: tmp.root, env: {} }),
      { path: "a.txt" },
    )
    expect(result.ok).toBe(false)
    expect(reasonOf(result)).toBe("no wechat recipient on this turn")
  })

  it("requires a string path", async () => {
    const tool = makeSendWechatFileTool(context())
    for (const args of [{}, { path: 7 }]) {
      const result = await call(tool, args)
      expect(result.ok).toBe(false)
      expect(reasonOf(result)).toBe("path is required")
    }
  })

  for (const tc of escapeCases()) {
    it(`rejects ${tc.label}`, async () => {
      makeEscapeSymlink(tmp)
      const result = await call(makeSendWechatFileTool(context()), { path: tc.path })
      expect(result.ok).toBe(false)
      expect(reasonOf(result)).toMatch(/outside the workspace/)
    })
  }

  it("enforces the media size gate", async () => {
    writeText(tmp.root, "ten.txt", "0123456789")
    const result = await call(
      makeSendWechatFileTool(context({ env: { WECHAT_MEDIA_MAX_BYTES: "4" } })),
      { path: "ten.txt" },
    )
    expect(result.ok).toBe(false)
    expect(reasonOf(result)).toBe("file exceeds 4 bytes")
  })

  it("fails closed when no sender is configured", async () => {
    writeText(tmp.root, "a.txt", "x")
    const result = await call(makeSendWechatFileTool(context()), { path: "a.txt" })
    expect(result.ok).toBe(false)
    expect(reasonOf(result)).toBe("WECHAT_TOKEN is not configured")
  })

  it("sends the workspace file through the injected sender", async () => {
    writeText(tmp.root, "note.txt", "payload")
    const captured: CapturedSend[] = []
    const tool = makeSendWechatFileTool(
      context({
        sendWechatMedia: async (input: {
          to: string
          fileName: string
          plaintext: Buffer
          caption?: string
        }) => {
          captured.push({
            to: input.to,
            fileName: input.fileName,
            plaintext: input.plaintext,
            ...(input.caption ? { caption: input.caption } : {}),
          })
          return { ok: true, value: { clientId: "c1", kind: "file" } }
        },
      }),
    )
    const result = await call(tool, { path: "note.txt", caption: "  日志  " })
    expect(result.ok).toBe(true)
    expect(outputOf(result)).toBe("已发送文件 note.txt")
    expect(captured).toHaveLength(1)
    expect(captured[0]?.to).toBe("user-1")
    expect(captured[0]?.fileName).toBe("note.txt")
    expect(captured[0]?.plaintext.toString("utf8")).toBe("payload")
    expect(captured[0]?.caption).toBe("日志")
  })
})
