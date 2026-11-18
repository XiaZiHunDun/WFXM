import { describe, expect, it } from "vitest"
import { buildApprovalNotice } from "./approval-notice.js"
import {
  MAX_REPLY_CHARS,
  MAX_WECHAT_MESSAGE_CHARS,
  finalizeReply,
  sanitizeForWechat,
  splitForWechat,
  taskStatusLabel,
  toolActionLabel,
} from "./presentation.js"

describe("toolActionLabel", () => {
  it("maps raw pi tool names to human actions", () => {
    expect(toolActionLabel("write")).toBe("修改文件")
    expect(toolActionLabel("edit")).toBe("修改文件")
    expect(toolActionLabel("bash")).toBe("执行命令")
    expect(toolActionLabel("read")).toBe("读取文件")
  })

  it("falls back instead of leaking an unknown tool name", () => {
    expect(toolActionLabel("mcp__internal__thing")).toBe("执行操作")
  })
})

describe("taskStatusLabel", () => {
  it("renders statuses users can read", () => {
    expect(taskStatusLabel("paused")).toBe("等待确认")
    expect(taskStatusLabel("running")).toBe("执行中")
    expect(taskStatusLabel("idle")).toBe("待命")
  })
})

describe("sanitizeForWechat", () => {
  it("drops markdown markers but keeps the content", () => {
    const input = [
      "# 排查步骤",
      "",
      "```ts",
      "const port = config.port",
      "```",
      "",
      "**重点**：先看 `gateway.log`。",
    ].join("\n")

    expect(sanitizeForWechat(input)).toBe(
      ["排查步骤", "", "const port = config.port", "", "重点：先看 gateway.log。"].join("\n"),
    )
  })

  it("keeps python-style dunder names intact", () => {
    expect(sanitizeForWechat("入口是 __main__ 模块")).toBe("入口是 __main__ 模块")
    expect(sanitizeForWechat("变量 __name__ 用于判断")).toBe("变量 __name__ 用于判断")
  })

  it("collapses runs of blank lines", () => {
    expect(sanitizeForWechat("一\n\n\n\n二")).toBe("一\n\n二")
  })

  it("drops horizontal rules that WeChat would render literally", () => {
    expect(sanitizeForWechat("结果如下\n\n---\n\n已经完成")).toBe("结果如下\n\n已经完成")
  })

  it("maps internal vocabulary to owner language", () => {
    expect(sanitizeForWechat("已派给 exec 子代理处理")).toBe("已派给执行代理处理")
    expect(sanitizeForWechat("已派给执行子代理处理")).toBe("已派给执行代理处理")
    expect(sanitizeForWechat("已写入 Durable Memory")).toBe("已写入长期记忆")
    expect(sanitizeForWechat("更新了 Project Knowledge")).toBe("更新了项目知识")
  })
})

describe("finalizeReply", () => {
  it("never returns an empty reply", () => {
    expect(finalizeReply("   ")).toContain("没有生成有效回复")
  })

  it("caps pathological lengths", () => {
    const reply = finalizeReply("字".repeat(MAX_REPLY_CHARS + 50))
    expect(reply.length).toBeLessThan(MAX_REPLY_CHARS + 40)
    expect(reply).toContain("已截断")
  })
})

describe("splitForWechat", () => {
  it("keeps a short reply in one part", () => {
    expect(splitForWechat("收到，正在处理。")).toEqual(["收到，正在处理。"])
  })

  it("splits on line boundaries and preserves order", () => {
    const lines = Array.from({ length: 60 }, (_, index) => `第 ${index + 1} 行：检查配置项。`)
    const parts = splitForWechat(lines.join("\n"), 120)

    expect(parts.length).toBeGreaterThan(1)
    for (const part of parts) expect(part.length).toBeLessThanOrEqual(120)
    expect(parts.join("\n")).toBe(lines.join("\n"))
  })

  it("hard-splits a single oversized line", () => {
    const parts = splitForWechat("甲".repeat(250), 100)
    expect(parts).toHaveLength(3)
    expect(parts.join("")).toHaveLength(250)
  })

  it("returns no part for blank content", () => {
    expect(splitForWechat("   ")).toEqual([])
  })
})

describe("user-facing message contract", () => {
  it("renders an approval that explains what will happen and how to answer", () => {
    const notice = buildApprovalNotice({
      taskId: "task-1",
      projectId: "p1",
      status: "paused",
      summary: "修复登录超时",
      pending: { toolName: "write", reason: "写入文件需要确认" },
    })

    expect(notice?.text).toBe(
      [
        "任务 task-1 需要确认",
        "目标：修复登录超时",
        "待执行：修改文件",
        "原因：写入文件需要确认",
        "回复「确认」继续，或「拒绝」取消。",
      ].join("\n"),
    )
    expect(notice?.text.length).toBeLessThan(MAX_WECHAT_MESSAGE_CHARS)
    expect(notice?.text).not.toMatch(/\*\*|```|^#{1,6}\s/m)
    expect(notice?.text).not.toMatch(/\b(write|edit|bash)\b/)
  })
})
