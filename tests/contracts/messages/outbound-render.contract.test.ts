// 锚定：出站回复「可发送性」契约 —— 长度上限、截断标记、空回复兜底、
// 内部术语/ markdown 不泄漏到用户可见文案。只断言外部可见结果，不比对完整文案。
// 说明：wechat-task-digest-reply 的 1500 字截断依赖 Wiring/DB，quality-gate 的
// truncate 是模块私有函数；两者属集成层（L2），此处用同一套最终出口
// (finalizeReply / splitForWechat) 与导出的通知渲染函数锚定同一条不变量。
import { describe, expect, it } from "vitest"
import {
  finalizeReply,
  MAX_REPLY_CHARS,
  MAX_WECHAT_MESSAGE_CHARS,
  sanitizeForWechat,
  splitForWechat,
} from "../../../packages/runtime/src/butler/presentation.js"
import {
  formatSubagentCompletionNotify,
  formatTaskRunCompletionNotify,
} from "../../../apps/api/src/wechat-run-notify.js"
import { mapChannelErrorToOwnerJargon } from "../../../apps/api/src/owner-jargon.js"
import { LONG_TEXT_200K, MIXED_TEXT } from "./messages-fixtures.js"

/** 通知类渲染的宽松可发送上限：远小于 WeChat 单条上限，且不随内部字段细节漂移。 */
const NOTIFY_MAX_CHARS = 800

describe("finalizeReply：最终出口的长度与兜底", () => {
  it("空/纯空白回复有非空兜底，且不返回空白串", () => {
    const empty = finalizeReply("")
    const blank = finalizeReply(" \n\t ")
    expect(empty.trim().length).toBeGreaterThan(0)
    expect(blank.trim().length).toBeGreaterThan(0)
    expect(empty).toBe(blank)
    expect(empty.length).toBeLessThanOrEqual(MAX_WECHAT_MESSAGE_CHARS)
  })

  it("超长回复被截断到上限附近并带截断标记", () => {
    const reply = finalizeReply(LONG_TEXT_200K)
    expect(reply.length).toBeGreaterThan(MAX_REPLY_CHARS)
    expect(reply.length).toBeLessThanOrEqual(MAX_REPLY_CHARS + 32)
    expect(reply).toContain("已截断")
    // 出口出口的文案不带首尾空白（可直接发送）。
    expect(reply).toBe(reply.trim())
  })

  it("多字节/emoji 长回复同样受上限约束", () => {
    const reply = finalizeReply(MIXED_TEXT.repeat(2_000))
    expect(reply.length).toBeLessThanOrEqual(MAX_REPLY_CHARS + 32)
    expect(reply).toContain("已截断")
    expect(reply.trim().length).toBeGreaterThan(0)
  })
})

describe("sanitizeForWechat：不把内部形态泄漏给用户", () => {
  it("去掉 markdown 标记但保留代码内容", () => {
    const raw = [
      "## 完成",
      "```ts",
      "const port = config.port",
      "```",
      "**要点**：先看 `gateway.log`。",
    ].join("\n")
    const out = sanitizeForWechat(raw)
    expect(out).not.toMatch(/```|\*\*|^#{1,6}\s/m)
    expect(out).toContain("const port = config.port")
    expect(out).toContain("gateway.log")
  })

  it("替换已知内部术语（子代理 / Durable Memory / Project Knowledge）", () => {
    const raw = "已派给 exec 子代理；已写入 Durable Memory；更新 Project Knowledge"
    const out = finalizeReply(raw)
    expect(out).not.toContain("子代理")
    expect(out).not.toContain("Durable Memory")
    expect(out).not.toContain("Project Knowledge")
    expect(out.trim().length).toBeGreaterThan(0)
  })

  it("不把原始工具名或 mcp_ 标识泄漏给用户（F-08）", () => {
    const out = finalizeReply("已调用 write_file 和 run_command，mcp_todoist_lst-tasks 完成")
    expect(out).not.toContain("write_file")
    expect(out).not.toContain("run_command")
    expect(out).not.toContain("mcp_")
    expect(out).toContain("修改文件")
  })

  it("不把工作区绝对路径泄漏给用户", () => {
    const out = finalizeReply(
      "改动落在 /home/ailearn/projects/WFXM/packages/runtime/src/a.ts 和 C:\\work\\repo\\b.ts",
    )
    expect(out).not.toContain("/home/")
    expect(out).not.toContain("C:\\work")
    expect(out).toContain("项目目录/a.ts")
    expect(out).toContain("项目目录/b.ts")
  })

  it("剥离不可见控制字符，仅剩控制字符时走兜底（F-06）", () => {
    // eslint-disable-next-line no-control-regex -- asserting C0/C1 controls are removed
    const CONTROL = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F]/
    expect(finalizeReply("\u0000\u0007\u001b[31m")).not.toMatch(CONTROL)
    const onlyControls = finalizeReply("\u0000\u0007")
    expect(onlyControls.trim().length).toBeGreaterThan(0)
    // eslint-disable-next-line no-control-regex -- asserting NUL/BEL are removed
    expect(onlyControls).not.toMatch(/[\u0000-\u0008]/)
  })
})

describe("splitForWechat：分条后可发送", () => {
  it("超长单行被切成多段，每段不超上限且不丢字符", () => {
    const parts = splitForWechat(LONG_TEXT_200K)
    expect(parts.length).toBeGreaterThan(1)
    for (const part of parts) {
      expect(part.length).toBeLessThanOrEqual(MAX_WECHAT_MESSAGE_CHARS)
      expect(part.trim().length).toBeGreaterThan(0)
    }
    expect(parts.join("")).toBe(LONG_TEXT_200K)
  })

  it("emoji + 中英混合长文本分条不丢非空白字符", () => {
    const raw = MIXED_TEXT.repeat(400)
    const parts = splitForWechat(raw)
    expect(parts.length).toBeGreaterThan(1)
    for (const part of parts) {
      expect(part.length).toBeLessThanOrEqual(MAX_WECHAT_MESSAGE_CHARS)
    }
    const stripWhitespace = (text: string): string => text.replace(/\s+/g, "")
    expect(stripWhitespace(parts.join(""))).toBe(stripWhitespace(raw))
  })

  it("纯空白内容不产生任何待发送分段", () => {
    expect(splitForWechat(" \n\t ")).toEqual([])
  })

  it("不在 emoji 代理对中间切断，拼接后与原文一致（F-07）", () => {
    const raw = "a" + "🚀".repeat(200)
    const parts = splitForWechat(raw, 100)
    for (const part of parts) {
      expect(part.length).toBeLessThanOrEqual(100)
      // 每段都不应以孤立的高代理项结尾。
      const last = part.charCodeAt(part.length - 1)
      expect(last >= 0xd800 && last <= 0xdbff).toBe(false)
    }
    expect(parts.join("")).toBe(raw)
  })

  it("最终出口组合（finalizeReply → splitForWechat）对 200k 输入仍可发送", () => {
    const parts = splitForWechat(finalizeReply(LONG_TEXT_200K))
    expect(parts.length).toBeGreaterThan(1)
    for (const part of parts) {
      expect(part.length).toBeLessThanOrEqual(MAX_WECHAT_MESSAGE_CHARS)
      expect(part.trim().length).toBeGreaterThan(0)
    }
    expect(parts.join("")).toContain("已截断")
  })
})

interface NotifierCase {
  readonly name: string
  readonly format: (reply: string) => string
}

const NOTIFIERS: readonly NotifierCase[] = [
  {
    name: "待办完成通知",
    format: (reply) =>
      formatTaskRunCompletionNotify({
        taskId: "task-abcdefghij",
        title: "修复登录超时",
        decision: "Respond",
        reply,
        ok: true,
      }),
  },
  {
    name: "子代理完成通知",
    format: (reply) =>
      formatSubagentCompletionNotify({
        role: "developer",
        task: "整理测试报告",
        reply,
        ok: true,
      }),
  },
]

describe.each(NOTIFIERS)("$name：可发送性", (notifier) => {
  it("超长回复只保留有界摘要，不整段外发", () => {
    const longReply = "哈".repeat(5_000)
    const text = notifier.format(longReply)
    expect(text.length).toBeLessThanOrEqual(NOTIFY_MAX_CHARS)
    expect(text).toContain("回复：")
    expect(text).not.toContain(longReply.slice(0, 1_000))
  })

  it("空回复不产生悬空的「回复：」行，整体仍非空", () => {
    const text = notifier.format("   ")
    expect(text).not.toContain("回复：")
    expect(text.trim().length).toBeGreaterThan(0)
    expect(text.split("\n").every((line) => line.length > 0)).toBe(true)
  })
})

describe("通知渲染：超长标题/任务文本不放大消息", () => {
  it("待办通知的标题被压缩", () => {
    const text = formatTaskRunCompletionNotify({
      taskId: "task-abcdefghij",
      title: "标".repeat(2_000),
      decision: "Respond",
      reply: "完成",
      ok: true,
    })
    expect(text.length).toBeLessThanOrEqual(NOTIFY_MAX_CHARS)
    expect(text).not.toContain("标".repeat(200))
  })

  it("子代理通知的任务描述被压缩", () => {
    const text = formatSubagentCompletionNotify({
      role: "developer",
      task: "任".repeat(2_000),
      reply: "完成",
      ok: true,
    })
    expect(text.length).toBeLessThanOrEqual(NOTIFY_MAX_CHARS)
    expect(text).not.toContain("任".repeat(200))
  })
})

describe("mapChannelErrorToOwnerJargon：上游错误不原样外发", () => {
  const CASES = [
    {
      name: "聊天不存在",
      raw: "Bad Request: chat not found",
      forbidden: ["Bad Request", "chat not found"],
    },
    {
      name: "被用户屏蔽",
      raw: "Forbidden: bot was blocked by the user",
      forbidden: ["Forbidden", "blocked"],
    },
    { name: "HTTP 状态", raw: "telegram API HTTP 502", forbidden: ["HTTP", "API"] },
    { name: "网络异常", raw: "socket hang up ECONNRESET", forbidden: ["socket", "ECONNRESET"] },
    {
      name: "唯一约束",
      raw: "duplicate key value violates unique constraint users_pkey",
      forbidden: ["duplicate key", "unique constraint"],
    },
  ] as const

  for (const testCase of CASES) {
    it(`${testCase.name}：转为非空中文说明且不含原始英文片段`, () => {
      const out = mapChannelErrorToOwnerJargon(testCase.raw)
      expect(out.trim().length).toBeGreaterThan(0)
      for (const forbidden of testCase.forbidden) {
        expect(out).not.toContain(forbidden)
      }
    })
  }
})
