import { mkdtempSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, describe, expect, it, vi } from "vitest"
import { runTool } from "@butler/runtime/tool-runtime.js"
import { makeSendWechatFileTool } from "./send-wechat-file.js"

describe("makeSendWechatFileTool", () => {
  let root: string

  afterEach(() => {
    if (root) rmSync(root, { recursive: true, force: true })
  })

  it("sends a jpeg inside the workspace via the injected uploader", async () => {
    root = mkdtempSync(join(tmpdir(), "wx-send-"))
    writeFileSync(join(root, "photo.jpg"), Buffer.from([0xff, 0xd8, 0xff, 0xd9]))
    const sendWechatMedia = vi.fn(async () => ({
      ok: true as const,
      value: { clientId: "c1", kind: "image" as const },
    }))
    const tool = makeSendWechatFileTool({
      workspaceRoot: root,
      wechatUserId: "u-wx",
      sendWechatMedia,
    })
    const result = await runTool(tool, { path: "photo.jpg", caption: "看图" }, { timeoutMs: 1000 })
    expect(result.ok).toBe(true)
    if (result.ok) expect(String(result.output)).toContain("图片")
    expect(sendWechatMedia).toHaveBeenCalledTimes(1)
    const arg = sendWechatMedia.mock.calls[0]?.[0]
    expect(arg?.to).toBe("u-wx")
    expect(arg?.fileName).toBe("photo.jpg")
    expect(arg?.caption).toBe("看图")
  })

  it("rejects a path outside the workspace", async () => {
    root = mkdtempSync(join(tmpdir(), "wx-send-"))
    const sendWechatMedia = vi.fn(async () => ({
      ok: true as const,
      value: { clientId: "c1", kind: "file" as const },
    }))
    const tool = makeSendWechatFileTool({
      workspaceRoot: root,
      wechatUserId: "u-wx",
      sendWechatMedia,
    })
    const result = await runTool(tool, { path: "/etc/passwd" }, { timeoutMs: 1000 })
    expect(result.ok).toBe(false)
    expect(sendWechatMedia).not.toHaveBeenCalled()
  })

  it("fails when there is no wechat recipient", async () => {
    root = mkdtempSync(join(tmpdir(), "wx-send-"))
    writeFileSync(join(root, "a.txt"), "x")
    const tool = makeSendWechatFileTool({ workspaceRoot: root })
    const result = await runTool(tool, { path: "a.txt" }, { timeoutMs: 1000 })
    expect(result.ok).toBe(false)
  })
})
