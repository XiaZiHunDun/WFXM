/**
 * R16 sandbox 扩面：MCP stdio spawn 在 bwrap 开关下的分支行为。
 * 用 vi.mock 拦截 child_process.spawn，验证 bwrap 是否被作为程序调起。
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest"

const spawnMock = vi.fn()
vi.mock("node:child_process", () => ({
  spawn: (...args: unknown[]) => spawnMock(...args),
}))

// 在 mock 之后导入（vitest hoists vi.mock）
const { nodeStdioSpawn } = await import("./mcp-spawn.js")

describe("nodeStdioSpawn sandbox gating (R16)", () => {
  const originalSandboxEnv = process.env["BUTLER_V5_SANDBOX"]

  beforeEach(() => {
    spawnMock.mockReset()
    // 模拟 child_process.spawn 的 EventEmitter-ish 行为
    spawnMock.mockImplementation(() => {
      return {
        stdout: { on: () => undefined },
        stderr: { on: () => undefined },
        stdin: { write: () => undefined, end: () => undefined },
        kill: () => undefined,
        on: () => undefined,
      }
    })
  })

  afterEach(() => {
    if (originalSandboxEnv === undefined) {
      delete process.env["BUTLER_V5_SANDBOX"]
    } else {
      process.env["BUTLER_V5_SANDBOX"] = originalSandboxEnv
    }
  })

  it("falls back to bare spawn when BUTLER_V5_SANDBOX unset", () => {
    delete process.env["BUTLER_V5_SANDBOX"]
    const child = nodeStdioSpawn("/usr/local/bin/my-mcp", ["--flag"], { env: {} })
    void child
    expect(spawnMock).toHaveBeenCalledTimes(1)
    const call = spawnMock.mock.calls[0] ?? []
    expect(call[0]).toBe("/usr/local/bin/my-mcp")
    expect(call[1]).toEqual(["--flag"])
  })

  it("wraps with bwrap when BUTLER_V5_SANDBOX=bubblewrap", () => {
    process.env["BUTLER_V5_SANDBOX"] = "bubblewrap"
    delete process.env["BUTLER_V5_SANDBOX_WORKSPACE_ROOT"]
    const child = nodeStdioSpawn("/usr/local/bin/my-mcp", ["--flag"], { env: {} })
    void child
    expect(spawnMock).toHaveBeenCalledTimes(1)
    const call = spawnMock.mock.calls[0] ?? []
    expect(call[0]).toBe("bwrap")
    const argv = call[1] as readonly string[]
    expect(argv).toContain("--die-with-parent")
    expect(argv).toContain("--unshare-net")
    // wrapped command 必须在 -- 之后
    const dashIdx = argv.indexOf("--")
    expect(argv[dashIdx + 1]).toBe("/usr/local/bin/my-mcp")
    expect(argv[dashIdx + 2]).toBe("--flag")
  })

  it("respects BUTLER_V5_SANDBOX_WORKSPACE_ROOT when set", () => {
    process.env["BUTLER_V5_SANDBOX"] = "bubblewrap"
    process.env["BUTLER_V5_SANDBOX_WORKSPACE_ROOT"] = "/tmp/ws-test"
    const child = nodeStdioSpawn("/usr/local/bin/my-mcp", [], { env: {} })
    void child
    const call = spawnMock.mock.calls[0] ?? []
    const argv = call[1] as readonly string[]
    expect(argv).toContain("/tmp/ws-test")
    // --bind workspace workspace 各出现两次（--bind + ws + ws）
    const bindIdx = argv.indexOf("--bind")
    expect(argv[bindIdx + 1]).toBe("/tmp/ws-test")
    expect(argv[bindIdx + 2]).toBe("/tmp/ws-test")
  })
})