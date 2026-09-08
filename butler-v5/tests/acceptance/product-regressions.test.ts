/**
 * 微信消息模拟验收 — 产品层回归锁（/undo 命令 + 垃圾消息护栏）。
 *
 * 脚本化 LLM(fixture) 驱动真实 `/v1/wechat/inbound`，不调真模型/真微信/真服务。
 *
 * 覆盖两个产品层真实修复的回归锁：
 *   1. `/undo <path>`：真实审批恢复 + undoLastWrite 还原内容。预先在工作区
 *      创建 `undo.txt=before`，fixture write_file 写 `after`，走完审批往返
 *      后 `/undo undo.txt` 必须还原文件内容，并回复 `已还原`。
 *   2. 垃圾消息护栏：发 `"请".repeat(80)`（单字符重复 80 次）必须被
 *      `detectSpam` 短路，回复命中 `消息过长|重复|具体需求`，且不消耗 LLM
 *      fixture（toolCalls=0，不含 fixture marker `SHOULD_NOT_BE_USED`）。
 *
 * 每个用例独立 conversationId，避免 ActiveMainRunConflict 跨用例污染。
 */
import { readFileSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import { afterAll, beforeAll, describe, expect, it } from "vitest"
import {
  makeAcceptanceApp,
  sendWechatMessage,
  textEntry,
  toolCallEntry,
  type AcceptanceApp,
} from "./harness.js"

describe("acceptance/product-regressions (微信产品层回归：/undo + 垃圾护栏)", () => {
  let app: AcceptanceApp

  beforeAll(async () => {
    app = await makeAcceptanceApp()
  })

  afterAll(async () => {
    await app.close()
  })

  it("/undo：真实审批后还原 write_file 写入", async () => {
    // 1. 预先在工作区根写入 `before`，让后续 write_file 的「pre-write content」
    //    栈帧能 pop 出 "before"。/undo 走 tryWechatUndoCommand → undoLastWrite
    //    → writeFileSync 写回。
    const undoPath = "undo.txt"
    const undoFile = join(app.workspaceRoot, undoPath)
    writeFileSync(undoFile, "before", "utf8")

    // 2. 单条 write_file fixture：写 `after`，期望触发 policy Ask →
    //    WaitForApproval（run paused）。
    app.setFixtures({
      plan: [toolCallEntry("write_file", { path: undoPath, content: "after" })],
    })

    const convId = "c-product-undo-regression"
    const first = await sendWechatMessage(app, {
      content: "帮我把 undo.txt 改成 after",
      conversationId: convId,
    })
    expect(first.status).toBe(201)
    expect(first.finalDecision).toBe("WaitForApproval")
    expect(first.conversationId).toBe(convId)

    // 3. 真实行内审批：`确认` 复用 waiting step → run 恢复 → write_file 实际
    //    执行（同时把 "before" 压栈 → 弹出 → 写入 "after"）。此时磁盘上
    //    undo.txt 应为 "after"。
    const approved = await sendWechatMessage(app, {
      content: "确认",
      conversationId: convId,
    })
    expect(approved.status).toBe(201)
    expect(approved.reply).toBeTypeOf("string")
    expect(approved.reply).not.toContain("没有待审批")
    expect(readFileSync(undoFile, "utf8")).toBe("after")

    // 4. /undo 命令：tryWechatUndoCommand 命中 → undoLastWrite 弹出 "before"
    //    → writeFileSync 还原。
    const undoRes = await sendWechatMessage(app, {
      content: `/undo ${undoPath}`,
      conversationId: convId,
    })
    expect(undoRes.status).toBe(201)
    expect(undoRes.reply).toContain("已还原")
    expect(readFileSync(undoFile, "utf8")).toBe("before")
  }, 30_000)

  it("垃圾消息护栏（spam guard）：`请`.repeat(80) 短路 LLM，命中重复字符提示", async () => {
    // fixture marker：若护栏失效让 LLM 跑了一次，回复里就会出现这条文案；
    // 用例断言 `not.toContain("SHOULD_NOT_BE_USED")` 即可证明 fixture 未被
    // 消费、护栏短路有效。
    app.setFixtures({
      plan: [textEntry("SHOULD_NOT_BE_USED fixture reply")],
    })

    // "请".repeat(80) = 80 个相同 CJK 字符（maxCount=80 > 30 && 占比=1.0 ≥ 0.3），
    // 命中 detectSpam 的"重复字符"分支（line 553）：`检测到字符「请」重复 80
    // 次。请发具体需求。`
    const res = await sendWechatMessage(app, {
      content: "请".repeat(80),
      conversationId: "c-product-spam-guard-regression",
    })
    expect(res.status).toBe(201)
    expect(res.reply).toMatch(/消息过长|重复|具体需求/)
    expect(res.toolCalls).toBe(0)
    expect(res.reply).not.toContain("SHOULD_NOT_BE_USED")
  }, 30_000)
})
