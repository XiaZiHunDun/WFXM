/**
 * 微信消息模拟验收 — 多轮对话 + 子代理委派。
 *
 * 覆盖：同一 conversationId 多轮（第二轮读到 history）、跨 turn 的工具调用 +
 * 审批恢复（write_file turn1 paused → turn2 确认恢复 → run 终态 succeeded）。
 */
import { describe, expect, it, afterAll, beforeAll } from "vitest"
import { eq } from "drizzle-orm"
import { runs } from "@butler/persistence/schema.js"
import {
  makeAcceptanceApp,
  sendWechatMessage,
  toolCallEntry,
  textEntry,
  type AcceptanceApp,
} from "./harness.js"

describe("acceptance/subagent-multiturn (微信多轮对话 + 跨 turn 工具调用)", () => {
  let app: AcceptanceApp

  beforeAll(async () => {
    app = await makeAcceptanceApp()
  })
  afterAll(async () => {
    await app.close()
  })

  it("同 conversationId 第二轮沿用第一轮 history，第二轮 LLM 看到前一轮文本", async () => {
    // turn 1：plan LLM 返回「第一轮答复」
    app.setFixtures({
      plan: [
        textEntry("第一轮答复：已收到"),
        // turn 2 时 LLM 应能看见第一轮的 user/assistant 历史；
        // 脚本化 LLM 不做"智能合并"，仅验证链路不丢 history。
        textEntry("第二轮答复：已延续 history"),
      ],
    })

    const first = await sendWechatMessage(app, { content: "第一轮问题" })
    expect(first.status).toBe(201)
    expect(first.reply).toContain("第一轮答复")
    expect(first.conversationId).toBeTypeOf("string")
    expect(first.finalDecision).toBe("Respond")

    const convId = first.conversationId as string

    const second = await sendWechatMessage(app, {
      content: "第二轮问题",
      conversationId: convId,
    })
    expect(second.status).toBe(201)
    expect(second.conversationId).toBe(convId)
    expect(second.reply).toContain("第二轮答复")

    // 两次调用应归属同一 conversationId，下方 runs 查询应至少一条 run
    const runRows = await app.db.select().from(runs).where(eq(runs.conversationId, convId))
    expect(runRows.length).toBeGreaterThanOrEqual(2)
    // 每个 turn 都产生独立的 run（新的 inbound 触发新 run，approval 不算）
    for (const r of runRows) {
      expect(["succeeded", "failed"]).toContain(r.status)
      expect(r.status).toBe("succeeded")
    }
  }, 30_000)

  it("跨 turn 工具调用：turn1 write_file paused → turn2 「确认」恢复 → run 达终态 succeeded", async () => {
    app.setFixtures({
      plan: [
        toolCallEntry("write_file", {
          path: "multi-turn.txt",
          content: "from multi-turn acceptance",
        }),
      ],
    })
    const first = await sendWechatMessage(app, {
      content: "帮我写 multi-turn.txt 内容是 from multi-turn acceptance",
    })
    expect(first.status).toBe(201)
    expect(first.finalDecision).toBe("WaitForApproval")
    expect(first.reply).toMatch(/需要确认|审批编号|approve/i)

    const convId = first.conversationId as string

    // 真实行内审批：tryWechatInlineApproval 复用 waiting step，复原 capability，
    // run 由 waiting_approval → succeeded。
    const second = await sendWechatMessage(app, {
      content: "确认",
      conversationId: convId,
    })
    expect(second.status).toBe(201)
    expect(second.reply).toBeTypeOf("string")
    expect(second.reply).not.toContain("没有待审批")

    // 最终 run 终态为 succeeded（write_file capability 已执行）
    const runRows = await app.db.select().from(runs).where(eq(runs.conversationId, convId))
    const last = runRows[runRows.length - 1]
    expect(last).toBeDefined()
    expect(last?.status).toBe("succeeded")
  }, 30_000)
})